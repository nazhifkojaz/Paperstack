import type { Rect } from '@/types/annotation';

interface AnnotationCreateOverlayProps {
  previewRect: Rect | null;
}

export function AnnotationCreateOverlay({ previewRect }: AnnotationCreateOverlayProps) {
  if (!previewRect) return null;

  return (
    <rect
      x={`${previewRect.x * 100}%`}
      y={`${previewRect.y * 100}%`}
      width={`${previewRect.w * 100}%`}
      height={`${previewRect.h * 100}%`}
      fill="transparent"
      stroke="#FF0000"
      strokeWidth={2}
      strokeDasharray="4 4"
      vectorEffect="non-scaling-stroke"
    />
  );
}
