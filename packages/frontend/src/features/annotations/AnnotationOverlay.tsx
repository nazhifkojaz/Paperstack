import { useMemo, useRef, useState, useEffect } from 'react';
import { StickyNote } from 'lucide-react';
import { useAnnotationStore } from '@/stores/annotationStore';
import { useCreateAnnotation } from '@/api/annotations';
import { useAnnotationsContext } from './AnnotationsContext';
import type { TextLayerHandle } from '@/types/viewer';
import type { Rect } from '@/types/annotation';
import { useTextMatcher } from './useTextMatcher';
import { useRectCreate } from './useRectCreate';
import { useAnnotationExplain } from './useAnnotationExplain';
import { NotePopover } from './NotePopover';
import { AnnotationToolbar } from './AnnotationToolbar';
import { AnnotationContextMenu } from './AnnotationContextMenu';
import { useAnnotationDrag } from './useAnnotationDrag';

interface AnnotationOverlayProps {
    pageNumber: number;
    pdfId: string;
    textLayerHandle?: React.RefObject<TextLayerHandle | null>;
    renderId?: number;
    className?: string;
}

export const AnnotationOverlay = ({ pageNumber, pdfId, textLayerHandle, renderId = 0, className = '' }: AnnotationOverlayProps) => {
    const isDrawingRect = useAnnotationStore(s => s.isDrawingRect);
    const selectedSetId = useAnnotationStore(s => s.selectedSetId);
    const selectedAnnotationId = useAnnotationStore(s => s.selectedAnnotationId);
    const contextMenu = useAnnotationStore(s => s.contextMenu);
    const setSelectedAnnotationId = useAnnotationStore(s => s.setSelectedAnnotationId);
    const setContextMenu = useAnnotationStore(s => s.setContextMenu);
    const setIsDrawingRect = useAnnotationStore(s => s.setIsDrawingRect);

    const { visibleSetIds, annotationsByPage } = useAnnotationsContext();
    const { mutate: createAnnotation } = useCreateAnnotation();

    // Build text-matcher input: own page + immediate neighbors (for fallback matching)
    const matcherAnnotations = useMemo(() => {
        const own = annotationsByPage.get(pageNumber) ?? [];
        const prev = annotationsByPage.get(pageNumber - 1) ?? [];
        const next = annotationsByPage.get(pageNumber + 1) ?? [];
        return [...own, ...prev, ...next];
    }, [annotationsByPage, pageNumber]);

    const containerRef = useRef<HTMLDivElement>(null);
    const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
    const [containerDims, setContainerDims] = useState<{ width: number; height: number } | null>(null);

    // Track container dimensions via ResizeObserver (avoids reading ref during render)
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const observer = new ResizeObserver(() => {
            setContainerDims({ width: el.offsetWidth, height: el.offsetHeight });
        });
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    const rectCreate = useRectCreate({
        containerRef,
        isDrawingRect,
        selectedSetId,
        onCreate: (rect) => {
            createAnnotation({
                set_id: selectedSetId!,
                page_number: pageNumber,
                type: 'rect',
                rects: [rect],
                color: '#FF0000',
            });
        },
        onDrawingEnd: () => setIsDrawingRect(false),
    });

    const annotationExplain = useAnnotationExplain({
        onSuccess: (_explanation, _noteContent, annotationId) => {
            setEditingNoteId(annotationId);
        },
    });

    const {
        isDragging,
        previewRect: dragPreviewRect,
        previewRects: dragPreviewRects,
        startResize,
        startMove,
    } = useAnnotationDrag(containerRef as React.RefObject<HTMLDivElement>);

    // Resolve empty-rect auto-highlight annotations via TextLayer DOM matching
    const resolvedAnnotations = useTextMatcher(matcherAnnotations, pageNumber, textLayerHandle, renderId);

    const pageAnnotations = useMemo(() => {
        return resolvedAnnotations.filter(a => a.page_number === pageNumber);
    }, [resolvedAnnotations, pageNumber]);

    const handleExplainThis = (annotationId: string) => {
        const ann = pageAnnotations.find(a => a.id === annotationId);
        if (!ann) return;

        setSelectedAnnotationId(annotationId);
        setEditingNoteId(annotationId);
        annotationExplain.explain(ann, pdfId);
    };

    if (visibleSetIds.length === 0 && !selectedSetId) return null;

    // Container pointer-events-none by default, pointer-events-auto cursor-crosshair when isDrawingRect
    const containerClasses = `absolute inset-0 z-30 ${isDrawingRect ? 'pointer-events-auto cursor-crosshair' : 'pointer-events-none'} ${className}`;

    return (
        <div
            ref={containerRef}
            className={containerClasses}
            onMouseDown={rectCreate.handleMouseDown}
            onMouseMove={rectCreate.handleMouseMove}
            onMouseUp={rectCreate.handleMouseUp}
            onMouseLeave={rectCreate.handleMouseLeave}
            onClick={(e) => {
                // If clicking directly on the overlay background (not on an annotation <g>),
                // clear the selection
                if (e.target === e.currentTarget) {
                    setSelectedAnnotationId(null);
                }
            }}
        >
            <svg className="w-full h-full" style={{ pointerEvents: 'none' }}>
                {pageAnnotations.map((ann) => {
                    const isSelected = selectedAnnotationId === ann.id;
                    const strokeColor = isSelected ? '#3b82f6' : (ann.color || '#FFFF00');
                    const strokeWidth = isSelected ? 3 : 2;

                    const effectiveRects = (isDragging && selectedAnnotationId === ann.id)
                        ? (dragPreviewRects || (dragPreviewRect ? [dragPreviewRect] : ann.rects))
                        : ann.rects;

                    return (
                        <g
                            key={ann.id}
                            pointerEvents="all"
                            onContextMenu={(e) => {
                                e.preventDefault();
                                setContextMenu({ x: e.clientX, y: e.clientY, annotationId: ann.id });
                                setSelectedAnnotationId(ann.id);
                            }}
                            onClick={(e) => {
                                e.stopPropagation();
                                setSelectedAnnotationId(ann.id);
                            }}
                            onMouseDown={(e) => {
                                if (selectedAnnotationId === ann.id && ann.type !== 'highlight') {
                                    e.stopPropagation();
                                    startMove(e, ann.rects);
                                }
                            }}
                        >
                            {ann.type === 'highlight' && effectiveRects.map((rect: Rect, idx: number) => (
                                <rect
                                    key={idx}
                                    x={`${rect.x * 100}%`}
                                    y={`${rect.y * 100}%`}
                                    width={`${rect.w * 100}%`}
                                    height={`${rect.h * 100}%`}
                                    rx={2}
                                    ry={2}
                                    fill={ann.color || '#FFFF00'}
                                    fillOpacity={0.4}
                                    style={{ mixBlendMode: 'multiply' }}
                                />
                            ))}

                            {ann.type === 'rect' && effectiveRects.map((rect: Rect, idx: number) => (
                                <rect
                                    key={idx}
                                    x={`${rect.x * 100}%`}
                                    y={`${rect.y * 100}%`}
                                    width={`${rect.w * 100}%`}
                                    height={`${rect.h * 100}%`}
                                    fill="transparent"
                                    stroke={strokeColor}
                                    strokeWidth={strokeWidth}
                                    vectorEffect="non-scaling-stroke"
                                />
                            ))}

                            {ann.type === 'note' && effectiveRects.length > 0 && (
                                <circle
                                    cx={`${(effectiveRects[0].x + effectiveRects[0].w / 2) * 100}%`}
                                    cy={`${(effectiveRects[0].y + effectiveRects[0].h / 2) * 100}%`}
                                    r={10}
                                    fill={ann.color || '#FF0000'}
                                    stroke={strokeColor}
                                    strokeWidth={strokeWidth}
                                    vectorEffect="non-scaling-stroke"
                                    pointerEvents="all"
                                    style={{ cursor: 'pointer' }}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setEditingNoteId(ann.id);
                                        setSelectedAnnotationId(ann.id);
                                    }}
                                />
                            )}
                        </g>
                    );
                })}

                {/* Resize handles for selected rect annotations */}
                {selectedAnnotationId && (() => {
                    const selectedAnn = pageAnnotations.find(a => a.id === selectedAnnotationId);
                    if (!selectedAnn || selectedAnn.type !== 'rect' || !selectedAnn.rects[0]) return null;

                    const rect = isDragging && dragPreviewRect
                        ? dragPreviewRect
                        : selectedAnn.rects[0];

                    const handles = [
                        { id: 'nw', x: rect.x, y: rect.y, cursor: 'nw-resize' },
                        { id: 'n', x: rect.x + rect.w / 2, y: rect.y, cursor: 'n-resize' },
                        { id: 'ne', x: rect.x + rect.w, y: rect.y, cursor: 'ne-resize' },
                        { id: 'e', x: rect.x + rect.w, y: rect.y + rect.h / 2, cursor: 'e-resize' },
                        { id: 'se', x: rect.x + rect.w, y: rect.y + rect.h, cursor: 'se-resize' },
                        { id: 's', x: rect.x + rect.w / 2, y: rect.y + rect.h, cursor: 's-resize' },
                        { id: 'sw', x: rect.x, y: rect.y + rect.h, cursor: 'sw-resize' },
                        { id: 'w', x: rect.x, y: rect.y + rect.h / 2, cursor: 'w-resize' },
                    ] as const;

                    return handles.map(handle => (
                        <rect
                            key={handle.id}
                            x={`${handle.x * 100 - 0.375}%`}
                            y={`${handle.y * 100 - 0.375}%`}
                            width="0.75%"
                            height="0.75%"
                            fill="white"
                            stroke="#3b82f6"
                            strokeWidth={1.5}
                            vectorEffect="non-scaling-stroke"
                            pointerEvents="all"
                            style={{ cursor: handle.cursor }}
                            onMouseDown={(e) => {
                                e.stopPropagation();
                                startResize(handle.id, e, rect);
                            }}
                        />
                    ));
                })()}

                {rectCreate.previewRect && (
                    <rect
                        x={`${rectCreate.previewRect.x * 100}%`}
                        y={`${rectCreate.previewRect.y * 100}%`}
                        width={`${rectCreate.previewRect.w * 100}%`}
                        height={`${rectCreate.previewRect.h * 100}%`}
                        fill="transparent"
                        stroke="#FF0000"
                        strokeWidth={2}
                        strokeDasharray="4 4"
                        vectorEffect="non-scaling-stroke"
                    />
                )}
            </svg>

            {/* Note Popover */}
            {editingNoteId && (() => {
                const noteAnn = pageAnnotations.find(a => a.id === editingNoteId);
                if (!noteAnn) return null;
                return (
                    <NotePopover
                        annotation={noteAnn}
                        containerDims={containerDims}
                        onClose={() => {
                            setEditingNoteId(null);
                            annotationExplain.clearExplain();
                        }}
                        isExplaining={annotationExplain.isExplaining && annotationExplain.explainingId === noteAnn.id}
                        explainStatusMessage={annotationExplain.statusMessage}
                    />
                );
            })()}

            {/* Note indicators for highlight/rect annotations that have note_content */}
            {containerDims && pageAnnotations
                .filter(ann => ann.type !== 'note' && ann.note_content)
                .map(ann => {
                    const rects = ann.rects;
                    const maxX = Math.max(...rects.map(r => r.x + r.w));
                    const minY = Math.min(...rects.map(r => r.y));
                    return (
                        <div
                            key={`note-indicator-${ann.id}`}
                            className="absolute z-40 pointer-events-auto"
                            style={{
                                left: `${maxX * containerDims.width}px`,
                                top: `${minY * containerDims.height}px`,
                                transform: 'translate(-50%, -50%)',
                            }}
                            title={ann.note_content ?? ''}
                            onClick={(e) => {
                                e.stopPropagation();
                                setEditingNoteId(ann.id);
                                setSelectedAnnotationId(ann.id);
                            }}
                        >
                            <StickyNote className="h-4 w-4 text-amber-500 drop-shadow-sm cursor-pointer" />
                        </div>
                    );
                })
            }

            {/* Annotation Toolbar */}
            {/* Hide toolbar when context menu is open to avoid duplicate color pickers */}
            {selectedAnnotationId && !contextMenu && (() => {
                const selectedAnn = pageAnnotations.find(a => a.id === selectedAnnotationId);
                if (!selectedAnn) return null;
                return (
                    <AnnotationToolbar
                        annotation={selectedAnn}
                        containerDims={containerDims}
                        onEditNote={() => setEditingNoteId(selectedAnnotationId)}
                    />
                );
            })()}

            {/* Context Menu (Task 6) */}
            {contextMenu && (() => {
                const contextAnnotation = pageAnnotations.find(a => a.id === contextMenu.annotationId);
                if (!contextAnnotation) return null;
                return (
                    <AnnotationContextMenu
                        annotation={contextAnnotation}
                        position={{ x: contextMenu.x, y: contextMenu.y }}
                        onClose={() => { setContextMenu(null); setSelectedAnnotationId(null); }}
                        onEditNote={(id) => setEditingNoteId(id)}
                        onExplainThis={handleExplainThis}
                        explainUsesRemaining={annotationExplain.explainUsesRemaining}
                    />
                );
            })()}
        </div>
    );
};
