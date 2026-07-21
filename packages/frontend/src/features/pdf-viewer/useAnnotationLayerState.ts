import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { RefObject } from 'react';
import { useAnnotationStore } from '@/stores/annotationStore';
import { useChatStore } from '@/stores/chatStore';
import { useInfoPanelCoordinator } from '@/hooks/useInfoPanelCoordinator';
import { useAnnotationsContext } from '@/features/annotations/AnnotationsContext';
import { useAnnotationExplain } from '@/features/annotations/useAnnotationExplain';
import { useAnnotationParaphrase } from '@/features/annotations/useAnnotationParaphrase';
import { useAnnotationDrag } from '@/features/annotations/useAnnotationDrag';
import type { Annotation } from '@/api/annotations';
import type { ParaphraseLevel } from '@/api/chat';
import type { Rect } from '@/types/annotation';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import {
  projectNormalizedRectsForRotation,
  textRangeToNormalizedRects,
} from './pdfGeometry';
import { useNewPdfViewerStore } from './pdfViewerStore';
import { useTextIndexMatcher } from './useTextIndexMatcher';
import type { PdfPageTextIndex, PdfViewportInfo } from './pdfViewerTypes';

export interface AnnotationLayerContainerDims {
  width: number;
  height: number;
}

export interface AnnotationLayerContextMenu {
  x: number;
  y: number;
  annotationId: string;
}

interface UseAnnotationLayerStateOptions {
  pageNumber: number;
  pdfId: string;
  textLayerRef?: RefObject<PdfTextLayerHandle | null>;
  renderId: number;
}

export function useAnnotationLayerState({
  pageNumber,
  pdfId,
  textLayerRef,
  renderId,
}: UseAnnotationLayerStateOptions) {
  const isDrawingRect = useAnnotationStore((s) => s.isDrawingRect);
  const selectedSetId = useAnnotationStore((s) => s.selectedSetId);
  const selectedAnnotationId = useAnnotationStore((s) => s.selectedAnnotationId);
  const contextMenu = useAnnotationStore(
    (s) => s.contextMenu,
  ) as AnnotationLayerContextMenu | null;
  const setSelectedAnnotationId = useAnnotationStore(
    (s) => s.setSelectedAnnotationId,
  );
  const setStoreContextMenu = useAnnotationStore((s) => s.setContextMenu);
  const setIsDrawingRect = useAnnotationStore((s) => s.setIsDrawingRect);

  const { visibleSetIds, annotationsByPage } = useAnnotationsContext();

  const containerRef = useRef<HTMLDivElement>(null);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [containerDims, setContainerDims] =
    useState<AnnotationLayerContainerDims | null>(null);
  const [containerElement, setContainerElement] =
    useState<HTMLDivElement | null>(null);
  const [textIndex, setTextIndex] = useState<PdfPageTextIndex | null>(null);

  const dimensions = useNewPdfViewerStore((s) =>
    s.pageDimensions.get(pageNumber),
  );
  const zoom = useNewPdfViewerStore((s) => s.zoom);
  const rotation = useNewPdfViewerStore((s) => s.rotation);

  const viewport: PdfViewportInfo | null = useMemo(
    () =>
      dimensions
        ? {
            width: dimensions.baseWidth,
            height: dimensions.baseHeight,
            rotation,
            scale: zoom,
          }
        : null,
    [dimensions, rotation, zoom],
  );

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

  useEffect(() => {
    const layer = textLayerRef?.current;
    if (!layer) return;

    layer.renderReady().then(() => {
      const index = textLayerRef.current?.getTextIndex?.();
      if (index) setTextIndex(index);
    });
  }, [textLayerRef, renderId]);

  const drag = useAnnotationDrag(containerRef as RefObject<HTMLDivElement>);

  const annotationExplain = useAnnotationExplain({
    onSuccess: (_explanation, _noteContent, annotationId) => {
      setEditingNoteId(annotationId);
    },
  });
  const annotationParaphrase = useAnnotationParaphrase({
    onSuccess: (_paraphrase, _noteContent, annotationId) => {
      setEditingNoteId(annotationId);
    },
  });

  const matcherAnnotations = useMemo(() => {
    const own = annotationsByPage.get(pageNumber) ?? [];
    const prev = annotationsByPage.get(pageNumber - 1) ?? [];
    const next = annotationsByPage.get(pageNumber + 1) ?? [];
    return [...own, ...prev, ...next];
  }, [annotationsByPage, pageNumber]);

  const resolvedAnnotations = useTextIndexMatcher(
    matcherAnnotations,
    pageNumber,
    textLayerRef as RefObject<PdfTextLayerHandle | null>,
    viewport,
    renderId,
  );

  const pageAnnotations = useMemo(
    () => resolvedAnnotations.filter((a) => a.page_number === pageNumber),
    [resolvedAnnotations, pageNumber],
  );

  const resolveRects = useCallback(
    (ann: Annotation): Rect[] => {
      if (drag.isDragging && selectedAnnotationId === ann.id) {
        if (drag.previewRects) return drag.previewRects;
        if (drag.previewRect) return [drag.previewRect];
      }

      const meta = ann.metadata as Record<string, unknown> | null | undefined;
      const resolver = meta?.resolver as { method?: string } | undefined;
      if (resolver?.method === 'selection' && ann.rects.length > 0) {
        return projectNormalizedRectsForRotation(ann.rects, rotation);
      }

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

      return projectNormalizedRectsForRotation(ann.rects, rotation);
    },
    [
      drag.isDragging,
      drag.previewRect,
      drag.previewRects,
      rotation,
      selectedAnnotationId,
      textIndex,
      viewport,
    ],
  );

  const openContextMenu = (menu: AnnotationLayerContextMenu) => {
    setStoreContextMenu(menu);
  };

  const closeContextMenu = () => {
    setStoreContextMenu(null);
    setSelectedAnnotationId(null);
  };

  const handleExplainThis = (annotationId: string) => {
    const ann = pageAnnotations.find((a) => a.id === annotationId);
    if (!ann) return;

    setSelectedAnnotationId(annotationId);
    setEditingNoteId(annotationId);
    annotationExplain.explain(ann, pdfId);
  };

  const handleParaphraseThis = (
    annotationId: string,
    level: ParaphraseLevel = 'same',
  ) => {
    const ann = pageAnnotations.find((a) => a.id === annotationId);
    if (!ann) return;

    setSelectedAnnotationId(annotationId);
    setEditingNoteId(annotationId);
    annotationParaphrase.paraphrase(ann, pdfId, level);
  };

  const setPendingAskQuote = useChatStore((s) => s.setPendingAskQuote);
  const openChat = useInfoPanelCoordinator().openChat;

  const handleAskInChat = (annotationId: string) => {
    const ann = pageAnnotations.find((a) => a.id === annotationId);
    if (!ann || !ann.selected_text) return;

    setSelectedAnnotationId(annotationId);
    setPendingAskQuote({
      text: ann.selected_text,
      pageNumber: ann.page_number,
    });
    openChat();
  };

  return {
    annotationExplain,
    annotationParaphrase,
    closeContextMenu,
    containerDims,
    containerElement,
    containerRef,
    contextMenu,
    drag,
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
  };
}
