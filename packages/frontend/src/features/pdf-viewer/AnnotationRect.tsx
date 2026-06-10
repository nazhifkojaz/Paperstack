import type { MouseEvent } from 'react';
import type { Annotation } from '@/api/annotations';
import type { Rect } from '@/types/annotation';
import { DEFAULT_HIGHLIGHT_COLOR } from '@/features/annotations/constants';

interface AnnotationRectProps {
  annotation: Annotation;
  rects: Rect[];
  isSelected: boolean;
  onContextMenu: (
    event: MouseEvent<SVGGElement>,
    annotationId: string,
  ) => void;
  onOpenNote: (annotationId: string) => void;
  onSelect: (annotationId: string) => void;
  onStartMove: (event: MouseEvent<SVGGElement>, rects: Rect[]) => void;
}

export function AnnotationRect({
  annotation,
  rects,
  isSelected,
  onContextMenu,
  onOpenNote,
  onSelect,
  onStartMove,
}: AnnotationRectProps) {
  const strokeColor = isSelected ? '#3b82f6' : annotation.color || DEFAULT_HIGHLIGHT_COLOR;
  const strokeWidth = isSelected ? 3 : 2;

  return (
    <g
      pointerEvents="all"
      onContextMenu={(event) => onContextMenu(event, annotation.id)}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(annotation.id);
      }}
      onMouseDown={(event) => {
        if (isSelected && annotation.type !== 'highlight') {
          event.stopPropagation();
          onStartMove(event, rects);
        }
      }}
    >
      {annotation.type === 'highlight' &&
        rects.map((rect, index) => (
          <rect
            key={index}
            x={`${rect.x * 100}%`}
            y={`${rect.y * 100}%`}
            width={`${rect.w * 100}%`}
            height={`${rect.h * 100}%`}
            rx={2}
            ry={2}
            fill={annotation.color || DEFAULT_HIGHLIGHT_COLOR}
            fillOpacity={0.4}
            style={{ mixBlendMode: 'multiply' }}
          />
        ))}

      {annotation.type === 'rect' &&
        rects.map((rect, index) => (
          <rect
            key={index}
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

      {annotation.type === 'note' && rects.length > 0 && (
        <circle
          cx={`${(rects[0].x + rects[0].w / 2) * 100}%`}
          cy={`${(rects[0].y + rects[0].h / 2) * 100}%`}
          r={10}
          fill={annotation.color || DEFAULT_HIGHLIGHT_COLOR}
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          vectorEffect="non-scaling-stroke"
          pointerEvents="all"
          style={{ cursor: 'pointer' }}
          onClick={(event) => {
            event.stopPropagation();
            onOpenNote(annotation.id);
            onSelect(annotation.id);
          }}
        />
      )}
    </g>
  );
}
