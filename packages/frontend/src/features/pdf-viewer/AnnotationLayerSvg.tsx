import type { MouseEvent } from 'react';
import type { Annotation } from '@/api/annotations';
import type { Rect } from '@/types/annotation';
import { AnnotationCreateOverlay } from './AnnotationCreateOverlay';
import { AnnotationRect } from './AnnotationRect';
import {
  AnnotationResizeHandles,
  type AnnotationResizeHandleId,
} from './AnnotationResizeHandles';
import type { AnnotationLayerContextMenu } from './useAnnotationLayerState';

interface AnnotationLayerSvgProps {
  annotations: Annotation[];
  createPreviewRect: Rect | null;
  dragPreviewRect: Rect | null;
  isDragging: boolean;
  resolveRects: (annotation: Annotation) => Rect[];
  selectedAnnotationId: string | null;
  onOpenContextMenu: (menu: AnnotationLayerContextMenu) => void;
  onOpenNote: (annotationId: string) => void;
  onSelectAnnotation: (annotationId: string | null) => void;
  onStartMove: (event: MouseEvent<SVGGElement>, rects: Rect[]) => void;
  onStartResize: (
    handleId: AnnotationResizeHandleId,
    event: MouseEvent<SVGRectElement>,
    rect: Rect,
  ) => void;
}

export function AnnotationLayerSvg({
  annotations,
  createPreviewRect,
  dragPreviewRect,
  isDragging,
  resolveRects,
  selectedAnnotationId,
  onOpenContextMenu,
  onOpenNote,
  onSelectAnnotation,
  onStartMove,
  onStartResize,
}: AnnotationLayerSvgProps) {
  const selectedAnnotation = selectedAnnotationId
    ? annotations.find((annotation) => annotation.id === selectedAnnotationId)
    : null;
  const selectedRects = selectedAnnotation ? resolveRects(selectedAnnotation) : [];
  const resizeRect =
    selectedAnnotation?.type === 'rect' && selectedRects[0]
      ? isDragging && dragPreviewRect
        ? dragPreviewRect
        : selectedRects[0]
      : null;

  return (
    <svg className="w-full h-full" style={{ pointerEvents: 'none' }}>
      {annotations.map((annotation) => {
        const rects = resolveRects(annotation);

        return (
          <AnnotationRect
            key={annotation.id}
            annotation={annotation}
            rects={rects}
            isSelected={selectedAnnotationId === annotation.id}
            onContextMenu={(event, annotationId) => {
              event.preventDefault();
              onOpenContextMenu({
                x: event.clientX,
                y: event.clientY,
                annotationId,
              });
              onSelectAnnotation(annotationId);
            }}
            onOpenNote={onOpenNote}
            onSelect={onSelectAnnotation}
            onStartMove={onStartMove}
          />
        );
      })}

      {resizeRect && (
        <AnnotationResizeHandles
          rect={resizeRect}
          onStartResize={onStartResize}
        />
      )}

      <AnnotationCreateOverlay previewRect={createPreviewRect} />
    </svg>
  );
}
