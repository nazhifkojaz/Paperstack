import type { MouseEvent } from 'react';
import type { Rect } from '@/types/annotation';

export type AnnotationResizeHandleId =
  | 'nw'
  | 'n'
  | 'ne'
  | 'e'
  | 'se'
  | 's'
  | 'sw'
  | 'w';

interface AnnotationResizeHandlesProps {
  rect: Rect;
  onStartResize: (
    handleId: AnnotationResizeHandleId,
    event: MouseEvent<SVGRectElement>,
    rect: Rect,
  ) => void;
}

export function AnnotationResizeHandles({
  rect,
  onStartResize,
}: AnnotationResizeHandlesProps) {
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

  return handles.map((handle) => (
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
      onMouseDown={(event) => onStartResize(handle.id, event, rect)}
    />
  ));
}
