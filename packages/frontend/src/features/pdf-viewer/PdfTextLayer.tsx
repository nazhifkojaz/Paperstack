import {
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import type { CSSProperties } from 'react';
import type { PDFPageProxy } from 'pdfjs-dist';
import { TextLayer as PdfjsTextLayer } from 'pdfjs-dist';
import { useNewPdfViewerStore } from './pdfViewerStore';
import {
  createPdfPageTextIndex,
} from './pdfTextIndex';
import type { PdfPageTextIndex, PdfTextItemGeometry } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Public handle exposed via ref
// ---------------------------------------------------------------------------

export interface PdfTextLayerHandle {
  /** The text layer DOM element. */
  getContainer: () => HTMLDivElement | null;
  /** Resolves when the current render cycle completes. */
  renderReady: () => Promise<void>;
  /** Raw text items from streamTextContent / getTextContent. */
  getTextItems: () => PdfTextItemGeometry[];
  /** Map from rendered <span> elements to text‑item indices. */
  getSpanToItemMap: () => Map<Element, number>;
  /** Current viewport zoom (used for coordinate conversion). */
  getViewportScale: () => number;
  /** Page‑level text index built from items. */
  getTextIndex: () => PdfPageTextIndex | null;
}

interface PdfTextLayerProps {
  pageProxy: PDFPageProxy | null;
  className?: string;
  onRenderComplete?: (renderId: number) => void;
}

const textContentParams = {
  includeMarkedContent: true,
  disableNormalization: true,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const PdfTextLayer = forwardRef<PdfTextLayerHandle, PdfTextLayerProps>(
  ({ pageProxy, className = '', onRenderComplete }, ref) => {
    const textLayerRef = useRef<HTMLDivElement>(null);
    const textLayerInstanceRef = useRef<PdfjsTextLayer | null>(null);
    const renderReadyResolveRef = useRef<() => void>(() => {});
    const renderReadyPromiseRef = useRef<Promise<void>>(Promise.resolve());
    const renderIdRef = useRef(0);

    // Text‑item cache
    const textItemsRef = useRef<PdfTextItemGeometry[]>([]);
    const spanToItemRef = useRef<Map<Element, number>>(new Map());
    const textIndexRef = useRef<PdfPageTextIndex | null>(null);

    const zoom = useNewPdfViewerStore((s) => s.zoom);
    const rotation = useNewPdfViewerStore((s) => s.rotation);

    // ---- Imperative handle ----
    useImperativeHandle(ref, () => ({
      getContainer: () => textLayerRef.current,
      renderReady: () => renderReadyPromiseRef.current,
      getTextItems: () => textItemsRef.current,
      getSpanToItemMap: () => spanToItemRef.current,
      getViewportScale: () => zoom,
      getTextIndex: () => textIndexRef.current,
    }));

    // ---- Render text layer ----
    useEffect(() => {
      if (!pageProxy || !textLayerRef.current) return;

      const container = textLayerRef.current;

      // Cancel stale render
      if (textLayerInstanceRef.current) {
        textLayerInstanceRef.current.cancel();
        textLayerInstanceRef.current = null;
      }

      // Reset cached mappings
      container.replaceChildren();
      textItemsRef.current = [];
      spanToItemRef.current = new Map();
      textIndexRef.current = null;

      const viewport = pageProxy.getViewport({ scale: zoom, rotation });

      const instance = new PdfjsTextLayer({
        textContentSource: pageProxy.streamTextContent(textContentParams),
        container,
        viewport,
      });
      textLayerInstanceRef.current = instance;
      let cleanupSelectionHelper: (() => void) | null = null;

      // Create a fresh ready promise
      renderReadyPromiseRef.current = new Promise<void>((resolve) => {
        renderReadyResolveRef.current = resolve;
      });

      instance
        .render()
        .then(async () => {
          if (textLayerInstanceRef.current !== instance) return;

          // Fetch full text content (includes items with transform data)
          const content = await pageProxy.getTextContent(textContentParams);

          const items: PdfTextItemGeometry[] = [];
          for (const item of content.items) {
            if (
              'str' in item &&
              typeof (item as Record<string, unknown>).str === 'string' &&
              (item as Record<string, unknown>).str
            ) {
              items.push(item as unknown as PdfTextItemGeometry);
            }
          }
          textItemsRef.current = items;

          // Map actual pdf.js text divs → item indices. Querying all spans is
          // unsafe because marked-content wrapper spans can appear in the DOM.
          const textDivs = (instance as unknown as { textDivs?: HTMLElement[] })
            .textDivs ?? Array.from(
              container.querySelectorAll<HTMLElement>('span[role="presentation"]'),
            );
          const map = new Map<Element, number>();
          const limit = Math.min(textDivs.length, items.length);
          for (let i = 0; i < limit; i++) {
            map.set(textDivs[i], i);
          }
          spanToItemRef.current = map;

          // Build the page text index (cached per render cycle)
          if (items.length > 0) {
            textIndexRef.current = createPdfPageTextIndex(
              items,
              pageProxy.pageNumber,
            );
          }

          renderIdRef.current++;
          onRenderComplete?.(renderIdRef.current);
          cleanupSelectionHelper = bindTextLayerSelectionHelper(container);
        })
        .then(() => {
          renderReadyResolveRef.current();
        })
        .catch((err: unknown) => {
          renderReadyResolveRef.current();
          if (
            err instanceof Error &&
            err.name === 'AbortException'
          )
            return;
          console.error('Failed to render text layer', err);
        });

      return () => {
        cleanupSelectionHelper?.();
        if (textLayerInstanceRef.current) {
          textLayerInstanceRef.current.cancel();
          textLayerInstanceRef.current = null;
        }
        renderReadyResolveRef.current();
        renderReadyPromiseRef.current = Promise.resolve();
      };
    }, [pageProxy, zoom, rotation, onRenderComplete]);

    if (!pageProxy) {
      return <div className={`absolute inset-0 z-20 ${className}`} />;
    }

    const viewport = pageProxy.getViewport({ scale: zoom, rotation });
    const textLayerStyle = {
      width: `${viewport.width}px`,
      height: `${viewport.height}px`,
      '--scale-factor': `${zoom}`,
      '--total-scale-factor': `${zoom}`,
      '--user-unit': '1',
      '--scale-round-x': '1px',
      '--scale-round-y': '1px',
      pointerEvents: 'auto',
      userSelect: 'text',
      cursor: 'text',
    } as CSSProperties;

    return (
      <div
        className={`absolute inset-0 z-20 ${className}`}
        style={{ pointerEvents: 'none' }}
      >
        <div
          ref={textLayerRef}
          className="absolute inset-0 pdfTextLayer"
          style={textLayerStyle}
        />
      </div>
    );
  },
);

PdfTextLayer.displayName = 'PdfTextLayer';

function bindTextLayerSelectionHelper(container: HTMLDivElement): () => void {
  const endDiv = document.createElement('div');
  endDiv.className = 'endOfContent';
  container.append(endDiv);

  let pointerDown = false;
  let previousRange: Range | null = null;

  const reset = () => {
    if (container.isConnected) container.append(endDiv);
    endDiv.style.width = '';
    endDiv.style.height = '';
    endDiv.style.userSelect = '';
    container.classList.remove('selecting');
    previousRange = null;
  };

  const onContainerMouseDown = () => {
    container.classList.add('selecting');
  };
  const onPointerDown = () => {
    pointerDown = true;
  };
  const onPointerUp = () => {
    pointerDown = false;
    reset();
  };
  const onBlur = () => {
    pointerDown = false;
    reset();
  };
  const onKeyUp = () => {
    if (!pointerDown) reset();
  };
  const onSelectionChange = () => {
    const selection = document.getSelection();
    if (!selection || selection.rangeCount === 0) {
      reset();
      return;
    }

    let intersectsContainer = false;
    for (let i = 0; i < selection.rangeCount; i++) {
      try {
        if (selection.getRangeAt(i).intersectsNode(container)) {
          intersectsContainer = true;
          break;
        }
      } catch {
        // Detached nodes can throw while pdf.js is re-rendering on zoom.
      }
    }
    if (!intersectsContainer) {
      reset();
      return;
    }

    container.classList.add('selecting');
    const range = selection.getRangeAt(0);
    const movingStart = previousRange !== null && (
      range.compareBoundaryPoints(Range.END_TO_END, previousRange) === 0 ||
      range.compareBoundaryPoints(Range.START_TO_END, previousRange) === 0
    );

    let anchor: Node | null = movingStart
      ? range.startContainer
      : range.endContainer;
    if (anchor?.nodeType === Node.TEXT_NODE) anchor = anchor.parentNode;

    if (!movingStart && range.endOffset === 0) {
      anchor = previousSelectableNode(anchor, container);
    }

    const anchorElement = anchor instanceof Element ? anchor : null;
    const anchorParent = anchorElement?.parentElement ?? null;
    const parentTextLayer = anchorParent?.closest('.pdfTextLayer');
    if (anchorElement && anchorParent && parentTextLayer === container) {
      endDiv.style.width = container.style.width;
      endDiv.style.height = container.style.height;
      endDiv.style.userSelect = 'text';
      anchorParent.insertBefore(
        endDiv,
        movingStart ? anchorElement : anchorElement.nextSibling,
      );
    }

    previousRange = range.cloneRange();
  };

  container.addEventListener('mousedown', onContainerMouseDown);
  document.addEventListener('pointerdown', onPointerDown);
  document.addEventListener('pointerup', onPointerUp);
  window.addEventListener('blur', onBlur);
  document.addEventListener('keyup', onKeyUp);
  document.addEventListener('selectionchange', onSelectionChange);

  return () => {
    container.removeEventListener('mousedown', onContainerMouseDown);
    document.removeEventListener('pointerdown', onPointerDown);
    document.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('blur', onBlur);
    document.removeEventListener('keyup', onKeyUp);
    document.removeEventListener('selectionchange', onSelectionChange);
    endDiv.remove();
  };
}

function previousSelectableNode(anchor: Node | null, boundary: HTMLElement): Node | null {
  let current = anchor;
  while (current && current !== boundary) {
    while (current && current !== boundary && !current.previousSibling) {
      current = current.parentNode;
    }
    if (!current || current === boundary) return anchor;

    current = current.previousSibling;
    if (!current) return anchor;
    while (current.lastChild) current = current.lastChild;
    if (current.textContent || current instanceof HTMLElement) return current;
  }

  return anchor;
}
