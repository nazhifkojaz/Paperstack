import type { RefObject } from 'react';
import { useCreateAnnotation } from '@/api/annotations';
import { useRectCreate } from '@/features/annotations/useRectCreate';
import type { Rect } from '@/types/annotation';
import { unprojectNormalizedRectForRotation } from './pdfGeometry';

interface UseAnnotationCreationOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  isDrawingRect: boolean;
  selectedSetId: string | null;
  pageNumber: number;
  rotation: number;
  onDrawingEnd: () => void;
}

export function useAnnotationCreation({
  containerRef,
  isDrawingRect,
  selectedSetId,
  pageNumber,
  rotation,
  onDrawingEnd,
}: UseAnnotationCreationOptions) {
  const { mutate: createAnnotation } = useCreateAnnotation();

  return useRectCreate({
    containerRef,
    isDrawingRect,
    selectedSetId,
    onCreate: (rect: Rect) => {
      if (!selectedSetId) return;

      const storedRect = unprojectNormalizedRectForRotation(rect, rotation);
      createAnnotation({
        set_id: selectedSetId,
        page_number: pageNumber,
        type: 'rect',
        rects: [storedRect],
        color: '#FF0000',
      });
    },
    onDrawingEnd,
  });
}
