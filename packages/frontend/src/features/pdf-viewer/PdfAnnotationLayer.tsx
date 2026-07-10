import type { MouseEvent, RefObject } from 'react';
import { AnnotationLayerSvg } from './AnnotationLayerSvg';
import { AnnotationLayerToolbar } from './AnnotationLayerToolbar';
import { useAnnotationCreation } from './useAnnotationCreation';
import { useAnnotationLayerState } from './useAnnotationLayerState';
import type { AnnotationResizeHandleId } from './AnnotationResizeHandles';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import type { Rect } from '@/types/annotation';

interface PdfAnnotationLayerProps {
  pageNumber: number;
  pdfId: string;
  textLayerRef?: RefObject<PdfTextLayerHandle | null>;
  renderId?: number;
  className?: string;
}

export const PdfAnnotationLayer = ({
  pageNumber,
  pdfId,
  textLayerRef,
  renderId = 0,
  className = '',
}: PdfAnnotationLayerProps) => {
  const {
    annotationExplain,
    annotationParaphrase,
    closeContextMenu,
    containerDims,
    containerElement,
    containerRef,
    contextMenu,
    drag: {
      isDragging,
      previewRect: dragPreviewRect,
      startMove,
      startResize,
    },
    editingNoteId,
    handleExplainThis,
    handleParaphraseThis,
    handleAskInChat,
    isDrawingRect,
    openContextMenu,
    pageAnnotations,
    resolveRects,
    rotation,
    selectedAnnotationId,
    selectedSetId,
    setEditingNoteId,
    setIsDrawingRect,
    setSelectedAnnotationId,
    visibleSetIds,
  } = useAnnotationLayerState({
    pageNumber,
    pdfId,
    textLayerRef,
    renderId,
  });

  const rectCreate = useAnnotationCreation({
    containerRef,
    isDrawingRect,
    selectedSetId,
    pageNumber,
    rotation,
    onDrawingEnd: () => setIsDrawingRect(false),
  });

  if (visibleSetIds.length === 0 && !selectedSetId) return null;

  const containerClasses = `absolute inset-0 z-30 ${
    isDrawingRect
      ? 'pointer-events-auto cursor-crosshair'
      : 'pointer-events-none'
  } ${className}`;

  const handleStartResize = (
    handleId: AnnotationResizeHandleId,
    event: MouseEvent<SVGRectElement>,
    rect: Rect,
  ) => {
    event.stopPropagation();
    startResize(handleId, event, rect);
  };

  const handleStartMove = (
    event: MouseEvent<SVGGElement>,
    rects: Rect[],
  ) => {
    event.stopPropagation();
    startMove(event, rects);
  };

  return (
    <div
      ref={containerRef}
      className={containerClasses}
      onMouseDown={rectCreate.handleMouseDown}
      onMouseMove={rectCreate.handleMouseMove}
      onMouseUp={rectCreate.handleMouseUp}
      onMouseLeave={rectCreate.handleMouseLeave}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          setSelectedAnnotationId(null);
        }
      }}
    >
      <AnnotationLayerSvg
        annotations={pageAnnotations}
        createPreviewRect={rectCreate.previewRect}
        dragPreviewRect={dragPreviewRect}
        isDragging={isDragging}
        resolveRects={resolveRects}
        selectedAnnotationId={selectedAnnotationId}
        onOpenContextMenu={openContextMenu}
        onOpenNote={setEditingNoteId}
        onSelectAnnotation={setSelectedAnnotationId}
        onStartMove={handleStartMove}
        onStartResize={handleStartResize}
      />

      <AnnotationLayerToolbar
        annotationExplain={annotationExplain}
        annotationParaphrase={annotationParaphrase}
        containerDims={containerDims}
        containerElement={containerElement}
        contextMenu={contextMenu}
        editingNoteId={editingNoteId}
        pageAnnotations={pageAnnotations}
        resolveRects={resolveRects}
        selectedAnnotationId={selectedAnnotationId}
        onCloseContextMenu={closeContextMenu}
        onEditNote={setEditingNoteId}
        onExplainThis={handleExplainThis}
        onParaphraseThis={handleParaphraseThis}
        onAskInChat={handleAskInChat}
        onSelectAnnotation={setSelectedAnnotationId}
      />
    </div>
  );
};
