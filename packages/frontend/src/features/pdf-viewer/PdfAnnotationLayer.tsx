import { useMemo, useRef, useState, useEffect } from 'react';
import { StickyNote } from 'lucide-react';
import { useAnnotationStore } from '@/stores/annotationStore';
import { useCreateAnnotation } from '@/api/annotations';
import { useAnnotationsContext } from '@/features/annotations/AnnotationsContext';
import { useRectCreate } from '@/features/annotations/useRectCreate';
import { useAnnotationExplain } from '@/features/annotations/useAnnotationExplain';
import { useAnnotationDrag } from '@/features/annotations/useAnnotationDrag';
import { NotePopover } from '@/features/annotations/NotePopover';
import { AnnotationToolbar } from '@/features/annotations/AnnotationToolbar';
import { AnnotationContextMenu } from '@/features/annotations/AnnotationContextMenu';
import type { Annotation } from '@/api/annotations';
import type { Rect } from '@/types/annotation';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import { textRangeToNormalizedRects } from './pdfGeometry';
import { useNewPdfViewerStore } from './pdfViewerStore';
import { useTextIndexMatcher } from './useTextIndexMatcher';
import type { PdfViewportInfo } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Interface
// ---------------------------------------------------------------------------

interface PdfAnnotationLayerProps {
  pageNumber: number;
  pdfId: string;
  textLayerRef?: React.RefObject<PdfTextLayerHandle | null>;
  renderId?: number;
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const PdfAnnotationLayer = ({
  pageNumber,
  pdfId,
  textLayerRef,
  renderId = 0,
  className = '',
}: PdfAnnotationLayerProps) => {
  // ---- Annotation store ----
  const isDrawingRect = useAnnotationStore((s) => s.isDrawingRect);
  const selectedSetId = useAnnotationStore((s) => s.selectedSetId);
  const selectedAnnotationId = useAnnotationStore((s) => s.selectedAnnotationId);
  const contextMenu = useAnnotationStore((s) => s.contextMenu);
  const setSelectedAnnotationId = useAnnotationStore((s) => s.setSelectedAnnotationId);
  const setContextMenu = useAnnotationStore((s) => s.setContextMenu);
  const setIsDrawingRect = useAnnotationStore((s) => s.setIsDrawingRect);

  // ---- Data from context ----
  const { visibleSetIds, annotationsByPage } = useAnnotationsContext();
  const { mutate: createAnnotation } = useCreateAnnotation();

  // ---- Local state ----
  const containerRef = useRef<HTMLDivElement>(null);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [containerDims, setContainerDims] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [containerElement, setContainerElement] =
    useState<HTMLDivElement | null>(null);
  const [textIndex, setTextIndex] = useState<ReturnType<
    NonNullable<PdfTextLayerHandle['getTextIndex']>
  > | null>(null);

  // ---- Viewport info for text-index-based rect resolution ----
  const dimensions = useNewPdfViewerStore((s) =>
    s.pageDimensions.get(pageNumber),
  );
  const zoom = useNewPdfViewerStore((s) => s.zoom);

  const viewport: PdfViewportInfo | null = useMemo(
    () =>
      dimensions
        ? {
            width: dimensions.baseWidth,
            height: dimensions.baseHeight,
            rotation: 0,
            scale: zoom,
          }
        : null,
    [dimensions, zoom],
  );

  // ---- ResizeObserver for container dimensions ----
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setContainerElement(el);
    const observer = new ResizeObserver(() => {
      setContainerDims({
        width: el.offsetWidth,
        height: el.offsetHeight,
      });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // ---- Cache text index from text layer for render-safe access ----
  useEffect(() => {
    const layer = textLayerRef?.current;
    if (!layer) return;
    layer.renderReady().then(() => {
      const index = textLayerRef.current?.getTextIndex?.();
      if (index) setTextIndex(index);
    });
  }, [textLayerRef, renderId]);

  // ---- Rect drawing ----
  const rectCreate = useRectCreate({
    containerRef: containerRef as React.RefObject<HTMLDivElement>,
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

  // ---- Annotation explain ----
  const annotationExplain = useAnnotationExplain({
    onSuccess: (_explanation, _noteContent, annotationId) => {
      setEditingNoteId(annotationId);
    },
  });

  // ---- Annotation drag (move/resize) ----
  const {
    isDragging,
    previewRect: dragPreviewRect,
    previewRects: dragPreviewRects,
    startResize,
    startMove,
  } = useAnnotationDrag(
    containerRef as React.RefObject<HTMLDivElement>,
  );

  // ---- Resolve empty‑rect auto‑highlight annotations via text index ----
  const matcherAnnotations = useMemo(() => {
    const own = annotationsByPage.get(pageNumber) ?? [];
    const prev = annotationsByPage.get(pageNumber - 1) ?? [];
    const next = annotationsByPage.get(pageNumber + 1) ?? [];
    return [...own, ...prev, ...next];
  }, [annotationsByPage, pageNumber]);

  const resolvedAnnotations = useTextIndexMatcher(
    matcherAnnotations,
    pageNumber,
    textLayerRef as React.RefObject<PdfTextLayerHandle | null>,
    viewport,
    renderId,
  );

  // ---- Page annotations (resolved) ----
  const pageAnnotations = useMemo(
    () => resolvedAnnotations.filter((a) => a.page_number === pageNumber),
    [resolvedAnnotations, pageNumber],
  );

  // ---- Resolve rects: selection-created highlights keep exact DOM rects ----
  const resolveRects = (ann: Annotation): Rect[] => {
    if (isDragging && selectedAnnotationId === ann.id) {
      if (dragPreviewRects) return dragPreviewRects;
      if (dragPreviewRect) return [dragPreviewRect];
    }

    const meta = ann.metadata as Record<string, unknown> | null | undefined;
    const resolver = meta?.resolver as { method?: string } | undefined;
    if (resolver?.method === 'selection' && ann.rects.length > 0) {
      return ann.rects;
    }

    // Try to derive rects from selector metadata + text index
    if (meta?.text_range && viewport && textIndex) {
      const tr = meta.text_range as {
        page: number;
        start: number;
        end: number;
      };
      const derived = textRangeToNormalizedRects(
        textIndex,
        tr.start,
        tr.end,
        viewport,
      );
      if (derived.length > 0) return derived;
    }

    return ann.rects;
  };

  // ---- Explain handler ----
  const handleExplainThis = (annotationId: string) => {
    const ann = pageAnnotations.find((a) => a.id === annotationId);
    if (!ann) return;
    setSelectedAnnotationId(annotationId);
    setEditingNoteId(annotationId);
    annotationExplain.explain(ann, pdfId);
  };

  if (visibleSetIds.length === 0 && !selectedSetId) return null;

  const containerClasses = `absolute inset-0 z-30 ${
    isDrawingRect
      ? 'pointer-events-auto cursor-crosshair'
      : 'pointer-events-none'
  } ${className}`;

  return (
    <div
      ref={containerRef}
      className={containerClasses}
      onMouseDown={rectCreate.handleMouseDown}
      onMouseMove={rectCreate.handleMouseMove}
      onMouseUp={rectCreate.handleMouseUp}
      onMouseLeave={rectCreate.handleMouseLeave}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          setSelectedAnnotationId(null);
        }
      }}
    >
      {/* ---- SVG overlay: highlights, rects, resize handles, drawing preview ---- */}
      <svg className="w-full h-full" style={{ pointerEvents: 'none' }}>
        {pageAnnotations.map((ann) => {
          const isSelected = selectedAnnotationId === ann.id;
          const strokeColor = isSelected
            ? '#3b82f6'
            : ann.color || '#FFFF00';
          const strokeWidth = isSelected ? 3 : 2;
          const effectiveRects = resolveRects(ann);

          return (
            <g
              key={ann.id}
              pointerEvents="all"
              onContextMenu={(e) => {
                e.preventDefault();
                setContextMenu({
                  x: e.clientX,
                  y: e.clientY,
                  annotationId: ann.id,
                });
                setSelectedAnnotationId(ann.id);
              }}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedAnnotationId(ann.id);
              }}
              onMouseDown={(e) => {
                if (
                  selectedAnnotationId === ann.id &&
                  ann.type !== 'highlight'
                ) {
                  e.stopPropagation();
                  startMove(e, ann.rects);
                }
              }}
            >
              {/* Highlight rects */}
              {ann.type === 'highlight' &&
                effectiveRects.map((r, i) => (
                  <rect
                    key={i}
                    x={`${r.x * 100}%`}
                    y={`${r.y * 100}%`}
                    width={`${r.w * 100}%`}
                    height={`${r.h * 100}%`}
                    rx={2}
                    ry={2}
                    fill={ann.color || '#FFFF00'}
                    fillOpacity={0.4}
                    style={{ mixBlendMode: 'multiply' }}
                  />
                ))}

              {/* Rect outlines */}
              {ann.type === 'rect' &&
                effectiveRects.map((r, i) => (
                  <rect
                    key={i}
                    x={`${r.x * 100}%`}
                    y={`${r.y * 100}%`}
                    width={`${r.w * 100}%`}
                    height={`${r.h * 100}%`}
                    fill="transparent"
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}

              {/* Note indicators */}
              {ann.type === 'note' &&
                effectiveRects.length > 0 && (
                  <circle
                    cx={`${
                      (effectiveRects[0].x + effectiveRects[0].w / 2) *
                      100
                    }%`}
                    cy={`${
                      (effectiveRects[0].y + effectiveRects[0].h / 2) *
                      100
                    }%`}
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

        {/* Resize handles for selected rect */}
        {selectedAnnotationId &&
          (() => {
            const selectedAnn = pageAnnotations.find(
              (a) => a.id === selectedAnnotationId,
            );
            if (
              !selectedAnn ||
              selectedAnn.type !== 'rect' ||
              !selectedAnn.rects[0]
            )
              return null;

            const rect =
              isDragging && dragPreviewRect
                ? dragPreviewRect
                : selectedAnn.rects[0];

            const handles = [
              {
                id: 'nw',
                x: rect.x,
                y: rect.y,
                cursor: 'nw-resize',
              },
              {
                id: 'n',
                x: rect.x + rect.w / 2,
                y: rect.y,
                cursor: 'n-resize',
              },
              {
                id: 'ne',
                x: rect.x + rect.w,
                y: rect.y,
                cursor: 'ne-resize',
              },
              {
                id: 'e',
                x: rect.x + rect.w,
                y: rect.y + rect.h / 2,
                cursor: 'e-resize',
              },
              {
                id: 'se',
                x: rect.x + rect.w,
                y: rect.y + rect.h,
                cursor: 'se-resize',
              },
              {
                id: 's',
                x: rect.x + rect.w / 2,
                y: rect.y + rect.h,
                cursor: 's-resize',
              },
              {
                id: 'sw',
                x: rect.x,
                y: rect.y + rect.h,
                cursor: 'sw-resize',
              },
              {
                id: 'w',
                x: rect.x,
                y: rect.y + rect.h / 2,
                cursor: 'w-resize',
              },
            ] as const;

            return handles.map((h) => (
              <rect
                key={h.id}
                x={`${h.x * 100 - 0.375}%`}
                y={`${h.y * 100 - 0.375}%`}
                width="0.75%"
                height="0.75%"
                fill="white"
                stroke="#3b82f6"
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
                pointerEvents="all"
                style={{ cursor: h.cursor }}
                onMouseDown={(e) => {
                  e.stopPropagation();
                  startResize(h.id, e, rect);
                }}
              />
            ));
          })()}

        {/* Rect drawing preview */}
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

      {/* ---- Note Popover ---- */}
      {editingNoteId &&
        (() => {
          const noteAnn = pageAnnotations.find(
            (a) => a.id === editingNoteId,
          );
          if (!noteAnn) return null;
          return (
            <NotePopover
              annotation={noteAnn}
              containerDims={containerDims}
              containerElement={containerElement}
              onClose={() => {
                setEditingNoteId(null);
                annotationExplain.clearExplain();
              }}
              isExplaining={
                annotationExplain.isExplaining &&
                annotationExplain.explainingId === noteAnn.id
              }
              explainStatusMessage={annotationExplain.statusMessage}
            />
          );
        })()}

      {/* ---- Note indicators for annotations with note_content ---- */}
      {containerDims &&
        pageAnnotations
          .filter((ann) => ann.type !== 'note' && ann.note_content)
          .map((ann) => {
            const rects = ann.rects;
            if (!rects.length) return null;
            const maxX = Math.max(...rects.map((r) => r.x + r.w));
            const minY = Math.min(...rects.map((r) => r.y));
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
          })}

      {/* ---- Annotation Toolbar ---- */}
      {selectedAnnotationId &&
        !contextMenu &&
        (() => {
          const selectedAnn = pageAnnotations.find(
            (a) => a.id === selectedAnnotationId,
          );
          if (!selectedAnn) return null;
          return (
            <AnnotationToolbar
              annotation={selectedAnn}
              containerDims={containerDims}
              onEditNote={() => setEditingNoteId(selectedAnnotationId)}
            />
          );
        })()}

      {/* ---- Context Menu ---- */}
      {contextMenu &&
        (() => {
          const contextAnn = pageAnnotations.find(
            (a) => a.id === contextMenu.annotationId,
          );
          if (!contextAnn) return null;
          return (
            <AnnotationContextMenu
              annotation={contextAnn}
              position={{ x: contextMenu.x, y: contextMenu.y }}
              onClose={() => {
                setContextMenu(null);
                setSelectedAnnotationId(null);
              }}
              onEditNote={(id) => setEditingNoteId(id)}
              onExplainThis={handleExplainThis}
              explainUsesRemaining={
                annotationExplain.explainUsesRemaining
              }
            />
          );
        })()}
    </div>
  );
};
