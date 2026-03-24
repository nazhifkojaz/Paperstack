import { useMemo, useRef, useState, useEffect } from 'react';
import { toast } from 'sonner';
import { StickyNote } from 'lucide-react';
import { useAnnotationStore } from '@/stores/annotationStore';
import { useAnnotationSets, useMultiSetAnnotations, useCreateAnnotation, useUpdateAnnotation } from '@/api/annotations';
import { useExplainAnnotation } from '@/api/chat';
import { useQueryClient } from '@tanstack/react-query';
import type { TextLayerHandle } from '@/features/viewer/TextLayer';
import { useTextMatcher } from './useTextMatcher';
import { NotePopover } from './NotePopover';
import { AnnotationToolbar } from './AnnotationToolbar';
import { AnnotationContextMenu } from './AnnotationContextMenu';
import { useAnnotationDrag } from './useAnnotationDrag';

interface AnnotationOverlayProps {
    pageNumber: number;
    pdfId: string;
    textLayerHandle?: React.RefObject<TextLayerHandle | null>;
    className?: string;
}

export const AnnotationOverlay = ({ pageNumber, pdfId, textLayerHandle, className = '' }: AnnotationOverlayProps) => {
    // Change 1: Remove activeTool references, use isDrawingRect instead
    const { isDrawingRect, selectedSetId, hiddenSetIds, selectedAnnotationId, setSelectedAnnotationId, contextMenu, setContextMenu, setIsDrawingRect } = useAnnotationStore();
    const { data: allSets } = useAnnotationSets(pdfId);
    const visibleSetIds = useMemo(
        () => (allSets ?? []).filter(s => !hiddenSetIds.has(s.id)).map(s => s.id),
        [allSets, hiddenSetIds],
    );
    const { data: annotations } = useMultiSetAnnotations(visibleSetIds);
    const { mutate: createAnnotation } = useCreateAnnotation();

    const containerRef = useRef<HTMLDivElement>(null);
    const [dragStart, setDragStart] = useState<{ x: number, y: number } | null>(null);
    const [dragCurrent, setDragCurrent] = useState<{ x: number, y: number } | null>(null);
    const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
    const [explainAnnotationId, setExplainAnnotationId] = useState<string | null>(null);
    const [explainStatusMessage, setExplainStatusMessage] = useState<string>('');

    const { mutate: updateAnnotation } = useUpdateAnnotation();
    const { mutate: explainAnnotation } = useExplainAnnotation();
    const queryClient = useQueryClient();

    // Change 2 & 3: Remove onDragMove from destructuring, wire onDragEndCallbackRef
    const {
        isDragging,
        previewRect: dragPreviewRect,
        previewRects: dragPreviewRects,
        startResize,
        startMove,
        onDragEnd,
        onDragEndCallbackRef,
    } = useAnnotationDrag(containerRef);

    // Change 3: Wire onDragEndCallbackRef
    const handleDragEnd = () => {
        const result = onDragEnd();
        if (!result) return;

        const ann = pageAnnotations.find(a => a.id === selectedAnnotationId);
        if (!ann) return;

        if (result.type === 'resize') {
            updateAnnotation({ id: ann.id, data: { rects: [result.rect] } });
        } else if (result.type === 'move') {
            updateAnnotation({ id: ann.id, data: { rects: result.rects } });
        }
    };

    onDragEndCallbackRef.current = handleDragEnd;

    // Change 4: Clear local drag state when isDrawingRect becomes false
    useEffect(() => {
        if (!isDrawingRect) {
            setDragStart(null);
            setDragCurrent(null);
        }
    }, [isDrawingRect]);

    // Clear annotation selection on scroll so the toolbar doesn't linger
    useEffect(() => {
        const handleScroll = () => setSelectedAnnotationId(null);
        document.addEventListener('scroll', handleScroll, true);
        return () => document.removeEventListener('scroll', handleScroll, true);
    }, [setSelectedAnnotationId]);

    // Clear annotation selection when clicking anywhere outside an annotation
    // (annotation <g> elements call e.stopPropagation() so they won't trigger this)
    useEffect(() => {
        const handleClick = () => setSelectedAnnotationId(null);
        document.addEventListener('click', handleClick);
        return () => document.removeEventListener('click', handleClick);
    }, [setSelectedAnnotationId]);

    // Resolve empty-rect auto-highlight annotations via TextLayer DOM matching
    const resolvedAnnotations = useTextMatcher(annotations, pageNumber, textLayerHandle);

    // Filter annotations for this page
    const pageAnnotations = useMemo(() => {
        return resolvedAnnotations.filter(a => a.page_number === pageNumber);
    }, [resolvedAnnotations, pageNumber]);

    const getNormalizedCoordinates = (e: React.MouseEvent) => {
        if (!containerRef.current) return null;
        const rect = containerRef.current.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) / rect.width,
            y: (e.clientY - rect.top) / rect.height,
        };
    };

    const handleMouseDown = (e: React.MouseEvent) => {
        // Only allow drawing when isDrawingRect is true
        if (!isDrawingRect || !selectedSetId) return;
        const coords = getNormalizedCoordinates(e);
        if (coords) {
            setDragStart(coords);
            setDragCurrent(coords);
        }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        // Change 2: Remove onDragMove call - hook handles it internally
        // The hook now uses document-level listeners
        if (!dragStart) return;
        const coords = getNormalizedCoordinates(e);
        if (coords) {
            setDragCurrent(coords);
        }
    };

    const handleMouseUp = () => {
        // Note: Drag end is handled by the hook via onDragEndCallbackRef
        // and document-level listeners

        if (!dragStart || !dragCurrent || !selectedSetId) {
            setDragStart(null);
            setDragCurrent(null);
            return;
        }

        const x = Math.min(dragStart.x, dragCurrent.x);
        const y = Math.min(dragStart.y, dragCurrent.y);
        const w = Math.abs(dragCurrent.x - dragStart.x);
        const h = Math.abs(dragCurrent.y - dragStart.y);

        if (w > 0.01 && h > 0.01) {
            createAnnotation({
                set_id: selectedSetId,
                page_number: pageNumber,
                type: 'rect',
                rects: [{ x, y, w, h }],
                color: '#FF0000',
            }, {
                onSuccess: () => {
                    // Change 10: One-shot rect - after creation, turn off drawing mode
                    setIsDrawingRect(false);
                },
            });
        }

        setDragStart(null);
        setDragCurrent(null);
    };

    const handleExplainThis = (annotationId: string) => {
        const ann = pageAnnotations.find(a => a.id === annotationId);
        if (!ann || !ann.selected_text) return;

        setSelectedAnnotationId(annotationId);
        setEditingNoteId(annotationId);
        setExplainAnnotationId(annotationId);
        setExplainStatusMessage('Generating explanation...');

        explainAnnotation(
            {
                pdf_id: pdfId,
                annotation_id: annotationId,
                selected_text: ann.selected_text,
                page_number: ann.page_number,
            },
            {
                onSuccess: (result) => {
                    // Synchronously update cache so NotePopover sees the new note_content
                    queryClient.setQueryData(
                        ['annotations', ann.set_id],
                        (old: any[] | undefined) => {
                            if (!old) return old;
                            return old.map(a =>
                                a.id === annotationId ? { ...a, note_content: result.note_content } : a
                            );
                        }
                    );
                    setExplainAnnotationId(null);
                    setExplainStatusMessage('');
                },
                onError: (err: Error) => {
                    setExplainAnnotationId(null);
                    setExplainStatusMessage('');
                    toast.error(`Explanation failed: ${err.message}`);
                },
            }
        );
    };

    if (visibleSetIds.length === 0 && !selectedSetId) return null;

    // Change 5: Container pointer-events-none by default, pointer-events-auto cursor-crosshair when isDrawingRect
    const containerClasses = `absolute inset-0 z-30 ${isDrawingRect ? 'pointer-events-auto cursor-crosshair' : 'pointer-events-none'} ${className}`;

    let createPreviewRect = null;
    if (dragStart && dragCurrent && isDrawingRect) {
        const x = Math.min(dragStart.x, dragCurrent.x);
        const y = Math.min(dragStart.y, dragCurrent.y);
        const w = Math.abs(dragCurrent.x - dragStart.x);
        const h = Math.abs(dragCurrent.y - dragStart.y);
        createPreviewRect = { x, y, w, h };
    }

    return (
        <div
            ref={containerRef}
            className={containerClasses}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => {
                setDragStart(null);
                setDragCurrent(null);
                // Note: onDragEnd is called by the hook's document-level listener
            }}
            onClick={(e) => {
                // If clicking directly on the overlay background (not on an annotation <g>),
                // clear the selection
                if (e.target === e.currentTarget) {
                    setSelectedAnnotationId(null);
                }
            }}
        >
            {/* Change 6: SVG pointer-events none */}
            <svg className="w-full h-full" style={{ pointerEvents: 'none' }}>
                {pageAnnotations.map((ann) => {
                    const isSelected = selectedAnnotationId === ann.id;
                    const strokeColor = isSelected ? '#3b82f6' : (ann.color || '#FFFF00');
                    const strokeWidth = isSelected ? 3 : 2;

                    // Compute effective rects during drag (preview or actual)
                    const effectiveRects = (isDragging && selectedAnnotationId === ann.id)
                        ? (dragPreviewRects || (dragPreviewRect ? [dragPreviewRect] : ann.rects))
                        : ann.rects;

                    return (
                        <g
                            key={ann.id}
                            // Change 7: g elements get pointerEvents="all" and onContextMenu
                            pointerEvents="all"
                            onContextMenu={(e) => {
                                e.preventDefault();
                                setContextMenu({ x: e.clientX, y: e.clientY, annotationId: ann.id });
                                setSelectedAnnotationId(ann.id);
                            }}
                            // Change 8: Remove activeTool === 'select' guards - always clickable
                            onClick={(e) => {
                                e.stopPropagation();
                                setSelectedAnnotationId(ann.id);
                            }}
                            onMouseDown={(e) => {
                                // Change 8: Remove activeTool guard - annotations always movable when selected
                                if (selectedAnnotationId === ann.id && ann.type !== 'highlight') {
                                    e.stopPropagation();
                                    startMove(e, ann.rects);
                                }
                            }}
                        >
                            {ann.type === 'highlight' && effectiveRects.map((rect: any, idx: number) => (
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

                            {ann.type === 'rect' && effectiveRects.map((rect: any, idx: number) => (
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
                {/* Change 12: Render toolbar whenever selectedAnnotationId is set (remove activeTool check) */}
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
                            // Change 11: Use pointerEvents="all" instead of className
                            pointerEvents="all"
                            style={{ cursor: handle.cursor }}
                            onMouseDown={(e) => {
                                e.stopPropagation();
                                startResize(handle.id, e, rect);
                            }}
                        />
                    ));
                })()}

                {createPreviewRect && (
                    <rect
                        x={`${createPreviewRect.x * 100}%`}
                        y={`${createPreviewRect.y * 100}%`}
                        width={`${createPreviewRect.w * 100}%`}
                        height={`${createPreviewRect.h * 100}%`}
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
                        containerRef={containerRef}
                        onClose={() => {
                            setEditingNoteId(null);
                            setExplainAnnotationId(null);
                            setExplainStatusMessage('');
                        }}
                        isExplaining={explainAnnotationId === noteAnn.id}
                        explainStatusMessage={explainStatusMessage}
                    />
                );
            })()}

            {/* Note indicators for highlight/rect annotations that have note_content */}
            {containerRef.current && pageAnnotations
                .filter(ann => ann.type !== 'note' && ann.note_content)
                .map(ann => {
                    const container = containerRef.current!;
                    const rects = ann.rects;
                    const maxX = Math.max(...rects.map(r => r.x + r.w));
                    const minY = Math.min(...rects.map(r => r.y));
                    return (
                        <div
                            key={`note-indicator-${ann.id}`}
                            className="absolute z-40 pointer-events-auto"
                            style={{
                                left: `${maxX * container.offsetWidth}px`,
                                top: `${minY * container.offsetHeight}px`,
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
            {/* Change 12: Render whenever selectedAnnotationId is set (no activeTool check) */}
            {/* Hide toolbar when context menu is open to avoid duplicate color pickers */}
            {selectedAnnotationId && !contextMenu && (() => {
                const selectedAnn = pageAnnotations.find(a => a.id === selectedAnnotationId);
                if (!selectedAnn) return null;
                return (
                    <AnnotationToolbar
                        annotation={selectedAnn}
                        containerRef={containerRef}
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
                    />
                );
            })()}
        </div>
    );
};
