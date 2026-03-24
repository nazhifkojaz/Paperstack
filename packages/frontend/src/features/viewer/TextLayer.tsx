import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import type { PDFPageProxy } from 'pdfjs-dist';
import { TextLayer as PdfjsTextLayer } from 'pdfjs-dist';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { SelectionPopup } from '@/features/annotations/SelectionPopup';
import { collectTextNodes, selectionRangeToRects } from './pdfTextUtils';
import type { PdfTextItem, PdfRectData } from './pdfTextUtils';

interface SelectionState {
    selectionRect: { x: number; y: number; width: number; height: number };
    normalizedRects: Array<{ x: number; y: number; w: number; h: number }>;
    selectedText: string;
}

export interface TextLayerHandle {
    getContainer: () => HTMLDivElement | null;
    renderReady: () => Promise<void>;
    /** PDF text items for precise rect computation (bypasses DOM scaleX) */
    getTextItems: () => PdfTextItem[];
    /** Mapping from span elements to text item indices */
    getSpanToItemMap: () => Map<Element, number>;
    /** Current viewport scale for converting PDF units to pixels */
    getViewportScale: () => number;
}

export type { PdfTextItem } from './pdfTextUtils';

interface TextLayerProps {
    pageProxy: PDFPageProxy | null;
    className?: string;
}

export const TextLayer = forwardRef<TextLayerHandle, TextLayerProps>(({ pageProxy, className = '' }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const { zoom, rotation } = usePdfViewerStore();
    const [selectionState, setSelectionState] = useState<SelectionState | null>(null);
    const textLayerRef = useRef<HTMLDivElement>(null);
    const textLayerInstanceRef = useRef<PdfjsTextLayer | null>(null);
    const renderReadyResolveRef = useRef<() => void>(() => {});
    const renderReadyPromiseRef = useRef<Promise<void>>(Promise.resolve());
    // PDF text content items for precise rect computation (bypasses DOM measurement)
    const textItemsRef = useRef<PdfTextItem[]>([]);
    const spanToItemRef = useRef<Map<Element, number>>(new Map());

    useImperativeHandle(ref, () => ({
        getContainer: () => textLayerRef.current,
        renderReady: () => renderReadyPromiseRef.current,
        getTextItems: () => textItemsRef.current,
        getSpanToItemMap: () => spanToItemRef.current,
        getViewportScale: () => zoom,
    }));

    // Render text layer using pdfjs TextLayer class (v5+)
    useEffect(() => {
        if (!pageProxy || !textLayerRef.current) return;

        const textLayer = textLayerRef.current;

        // Cancel any in-progress render
        if (textLayerInstanceRef.current) {
            textLayerInstanceRef.current.cancel();
            textLayerInstanceRef.current = null;
        }

        // Clear previous content and cached mappings
        textLayer.replaceChildren();
        textItemsRef.current = [];
        spanToItemRef.current = new Map();

        const viewport = pageProxy.getViewport({ scale: zoom, rotation });

        const instance = new PdfjsTextLayer({
            textContentSource: pageProxy.streamTextContent(),
            container: textLayer,
            viewport,
        });

        textLayerInstanceRef.current = instance;

        // Create a new ready promise for this render cycle
        renderReadyPromiseRef.current = new Promise<void>(resolve => {
            renderReadyResolveRef.current = resolve;
        });

        instance.render()
            .then(() => {
                // Fetch text content items and build span→item mapping
                // BEFORE resolving renderReady, so consumers (useTextMatcher)
                // can rely on PDF data being available.
                return pageProxy.getTextContent().then(content => {
                    if (textLayerInstanceRef.current !== instance) return; // stale
                    const items: PdfTextItem[] = [];
                    for (const item of content.items) {
                        if ('str' in item && (item as any).str) {
                            items.push(item as unknown as PdfTextItem);
                        }
                    }
                    textItemsRef.current = items;

                    // pdf.js creates spans in the same order as text items
                    // (skipping items with empty str). Map each span to its item.
                    const spans = textLayer.querySelectorAll('span');
                    const map = new Map<Element, number>();
                    const limit = Math.min(spans.length, items.length);
                    for (let i = 0; i < limit; i++) {
                        map.set(spans[i], i);
                    }
                    spanToItemRef.current = map;
                });
            })
            .then(() => {
                renderReadyResolveRef.current();
            })
            .catch((err: unknown) => {
                // Always resolve so consumers never hang
                renderReadyResolveRef.current();
                if (err instanceof Error && err.name === 'AbortException') return;
                console.error('Failed to render text layer', err);
            });

        return () => {
            if (textLayerInstanceRef.current) {
                textLayerInstanceRef.current.cancel();
                textLayerInstanceRef.current = null;
            }
            // Resolve any pending promise so hooks don't hang on cleanup
            renderReadyResolveRef.current();
            renderReadyPromiseRef.current = Promise.resolve();
        };
    }, [pageProxy, zoom, rotation]);

    const handleMouseUp = useCallback(() => {
        if (!textLayerRef.current || !pageProxy) return;

        // Small delay to ensure selection is complete
        setTimeout(() => {
            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0) return;

            const range = selection.getRangeAt(0);
            const selectedText = range.toString();

            // Ignore empty selections or selections outside our container
            if (!selectedText.trim() || !textLayerRef.current?.contains(range.commonAncestorContainer)) {
                setSelectionState(null);
                return;
            }

            const containerRect = textLayerRef.current.getBoundingClientRect();
            if (containerRect.width === 0 || containerRect.height === 0) return;

            // Build PDF coordinate data for precise rect computation
            const pdfData: PdfRectData | undefined =
                textItemsRef.current.length > 0 && spanToItemRef.current.size > 0
                    ? { textItems: textItemsRef.current, spanToItemMap: spanToItemRef.current, viewportScale: zoom }
                    : undefined;

            // Use shared utility: map DOM Range → character positions → precise rects
            const { textNodes } = collectTextNodes(textLayerRef.current);
            const normalizedRects = selectionRangeToRects(range, textNodes, containerRect, pdfData);

            if (normalizedRects.length === 0) {
                setSelectionState(null);
                return;
            }

            // Compute screen-coordinate bounding box for popup positioning
            const rangeBounds = range.getBoundingClientRect();
            const selectionRect = {
                x: rangeBounds.left,
                y: rangeBounds.top,
                width: rangeBounds.width,
                height: rangeBounds.height,
            };

            setSelectionState({
                selectionRect,
                normalizedRects,
                selectedText,
            });
            // Clear native selection — our SVG overlay provides the visual highlight
            window.getSelection()?.removeAllRanges();
        }, 10);
    }, [pageProxy, zoom, rotation]);

    const handleDismiss = useCallback(() => {
        setSelectionState(null);
        window.getSelection()?.removeAllRanges();
    }, []);

    if (!pageProxy) {
        return <div ref={containerRef} className={`absolute inset-0 z-20 ${className}`} />;
    }

    const viewport = pageProxy.getViewport({ scale: zoom, rotation });

    return (
        <div
            ref={containerRef}
            className={`absolute inset-0 z-20 ${className}`}
            style={{
                pointerEvents: 'none',
            }}
        >
            <div
                ref={textLayerRef}
                className="absolute inset-0 pdfTextLayer"
                style={{
                    width: `${viewport.width}px`,
                    height: `${viewport.height}px`,
                    pointerEvents: 'auto',
                    userSelect: 'text',
                    cursor: 'text',
                }}
                onMouseUp={handleMouseUp}
            >
                {/* Text divs rendered by pdfjsLib.renderTextLayer */}
            </div>

            {selectionState && (
                <>
                    <svg
                        className="absolute inset-0 pointer-events-none"
                        style={{ width: `${viewport.width}px`, height: `${viewport.height}px`, mixBlendMode: 'multiply' }}
                        aria-hidden
                    >
                        {selectionState.normalizedRects.map((r, i) => (
                            <rect
                                key={i}
                                x={r.x * viewport.width}
                                y={r.y * viewport.height}
                                width={r.w * viewport.width}
                                height={r.h * viewport.height}
                                rx={2}
                                ry={2}
                                fill="rgba(100, 160, 255, 0.4)"
                            />
                        ))}
                    </svg>
                    <SelectionPopup
                        selectionRect={selectionState.selectionRect}
                        normalizedRects={selectionState.normalizedRects}
                        selectedText={selectionState.selectedText}
                        pageNumber={pageProxy.pageNumber}
                        onDismiss={handleDismiss}
                    />
                </>
            )}
        </div>
    );
});

TextLayer.displayName = 'TextLayer';
