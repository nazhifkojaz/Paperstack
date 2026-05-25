import { StickyNote } from 'lucide-react';
import { AnnotationContextMenu } from '@/features/annotations/AnnotationContextMenu';
import { AnnotationToolbar } from '@/features/annotations/AnnotationToolbar';
import { NotePopover } from '@/features/annotations/NotePopover';
import type { Annotation } from '@/api/annotations';
import type { Rect } from '@/types/annotation';
import type {
  AnnotationLayerContainerDims,
  AnnotationLayerContextMenu,
} from './useAnnotationLayerState';

interface AnnotationExplainControls {
  clearExplain: () => void;
  explainUsesRemaining: number | null;
  explainingId: string | null;
  isExplaining: boolean;
  statusMessage: string;
}

interface AnnotationLayerToolbarProps {
  annotationExplain: AnnotationExplainControls;
  containerDims: AnnotationLayerContainerDims | null;
  containerElement: HTMLDivElement | null;
  contextMenu: AnnotationLayerContextMenu | null;
  editingNoteId: string | null;
  pageAnnotations: Annotation[];
  resolveRects: (annotation: Annotation) => Rect[];
  selectedAnnotationId: string | null;
  onCloseContextMenu: () => void;
  onEditNote: (annotationId: string | null) => void;
  onExplainThis: (annotationId: string) => void;
  onSelectAnnotation: (annotationId: string | null) => void;
}

export function AnnotationLayerToolbar({
  annotationExplain,
  containerDims,
  containerElement,
  contextMenu,
  editingNoteId,
  pageAnnotations,
  resolveRects,
  selectedAnnotationId,
  onCloseContextMenu,
  onEditNote,
  onExplainThis,
  onSelectAnnotation,
}: AnnotationLayerToolbarProps) {
  const getAnnotationWithRects = (annotationId: string | null) => {
    if (!annotationId) return null;
    const annotation = pageAnnotations.find((a) => a.id === annotationId);
    if (!annotation) return null;

    const rects = resolveRects(annotation);
    if (!rects.length) return null;

    return { annotation, rects };
  };

  const editingAnnotation = getAnnotationWithRects(editingNoteId);
  const selectedAnnotation = getAnnotationWithRects(selectedAnnotationId);
  const contextAnnotation = contextMenu
    ? pageAnnotations.find((a) => a.id === contextMenu.annotationId)
    : null;

  return (
    <>
      {editingAnnotation && (
        <NotePopover
          annotation={{
            ...editingAnnotation.annotation,
            rects: editingAnnotation.rects,
          }}
          containerDims={containerDims}
          containerElement={containerElement}
          onClose={() => {
            onEditNote(null);
            annotationExplain.clearExplain();
          }}
          isExplaining={
            annotationExplain.isExplaining &&
            annotationExplain.explainingId === editingAnnotation.annotation.id
          }
          explainStatusMessage={annotationExplain.statusMessage}
        />
      )}

      {containerDims &&
        pageAnnotations
          .filter((annotation) => annotation.type !== 'note' && annotation.note_content)
          .map((annotation) => {
            const rects = resolveRects(annotation);
            if (!rects.length) return null;

            const maxX = Math.max(...rects.map((rect) => rect.x + rect.w));
            const minY = Math.min(...rects.map((rect) => rect.y));

            return (
              <div
                key={`note-indicator-${annotation.id}`}
                className="absolute z-40 pointer-events-auto"
                style={{
                  left: `${maxX * containerDims.width}px`,
                  top: `${minY * containerDims.height}px`,
                  transform: 'translate(-50%, -50%)',
                }}
                title={annotation.note_content ?? ''}
                onClick={(event) => {
                  event.stopPropagation();
                  onEditNote(annotation.id);
                  onSelectAnnotation(annotation.id);
                }}
              >
                <StickyNote className="h-4 w-4 text-amber-500 drop-shadow-sm cursor-pointer" />
              </div>
            );
          })}

      {selectedAnnotation && !contextMenu && (
        <AnnotationToolbar
          annotation={{
            ...selectedAnnotation.annotation,
            rects: selectedAnnotation.rects,
          }}
          containerDims={containerDims}
          onEditNote={() => onEditNote(selectedAnnotationId)}
        />
      )}

      {contextMenu && contextAnnotation && (
        <AnnotationContextMenu
          annotation={contextAnnotation}
          position={{ x: contextMenu.x, y: contextMenu.y }}
          onClose={onCloseContextMenu}
          onEditNote={onEditNote}
          onExplainThis={onExplainThis}
          explainUsesRemaining={annotationExplain.explainUsesRemaining}
        />
      )}
    </>
  );
}
