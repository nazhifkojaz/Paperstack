import { StickyNote } from 'lucide-react';
import { AnnotationContextMenu } from '@/features/annotations/AnnotationContextMenu';
import { AnnotationToolbar } from '@/features/annotations/AnnotationToolbar';
import { NotePopover } from '@/features/annotations/NotePopover';
import {
  getAnnotationSupplementalTitle,
  hasAnnotationSupplementalContent,
} from '@/features/annotations/annotationContent';
import type { Annotation } from '@/api/annotations';
import type { ParaphraseLevel } from '@/api/chat';
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

interface AnnotationParaphraseControls {
  clearParaphrase: () => void;
  explainUsesRemaining: number | null;
  isParaphrasing: boolean;
  paraphrasingId: string | null;
  statusMessage: string;
}

interface AnnotationLayerToolbarProps {
  annotationExplain: AnnotationExplainControls;
  annotationParaphrase: AnnotationParaphraseControls;
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
  onParaphraseThis: (annotationId: string, level?: ParaphraseLevel) => void;
  onSelectAnnotation: (annotationId: string | null) => void;
}

export function AnnotationLayerToolbar({
  annotationExplain,
  annotationParaphrase,
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
  onParaphraseThis,
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
            annotationParaphrase.clearParaphrase();
          }}
          isExplaining={
            annotationExplain.isExplaining &&
            annotationExplain.explainingId === editingAnnotation.annotation.id
          }
          explainStatusMessage={annotationExplain.statusMessage}
          onExplainThis={onExplainThis}
          isParaphrasing={
            annotationParaphrase.isParaphrasing &&
            annotationParaphrase.paraphrasingId === editingAnnotation.annotation.id
          }
          paraphraseStatusMessage={annotationParaphrase.statusMessage}
          onParaphraseThis={onParaphraseThis}
        />
      )}

      {containerDims &&
        pageAnnotations
          .filter(
            (annotation) =>
              annotation.type !== 'note' &&
              hasAnnotationSupplementalContent(annotation),
          )
          .map((annotation) => {
            const rects = resolveRects(annotation);
            if (!rects.length) return null;
            const noteTitle = getAnnotationSupplementalTitle(annotation);

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
                title={noteTitle}
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
          onParaphraseThis={onParaphraseThis}
          aiUsesRemaining={
            annotationParaphrase.explainUsesRemaining ??
            annotationExplain.explainUsesRemaining
          }
        />
      )}
    </>
  );
}
