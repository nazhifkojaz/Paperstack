import { useUpdateAnnotation, type Annotation } from '@/api/annotations';
import { Check, StickyNote } from 'lucide-react';

const COLOR_PRESETS = [
    { color: '#EF4444', label: 'Red' },
    { color: '#3B82F6', label: 'Blue' },
    { color: '#22C55E', label: 'Green' },
    { color: '#FFFF00', label: 'Yellow' },
    { color: '#F97316', label: 'Orange' },
    { color: '#A855F7', label: 'Purple' },
];

interface AnnotationToolbarProps {
    annotation: Annotation;
    containerRef: React.RefObject<HTMLDivElement | null>;
    onEditNote: () => void;
}

export const AnnotationToolbar = ({ annotation, containerRef, onEditNote }: AnnotationToolbarProps) => {
    const { mutate: updateAnnotation } = useUpdateAnnotation();

    const handleColorChange = (color: string) => {
        updateAnnotation({ id: annotation.id, data: { color } });
    };

    // Compute position from normalized coordinates
    const container = containerRef.current;
    if (!container || !annotation.rects[0]) return null;

    // Use bounding box of all rects
    const rects = annotation.rects;
    const minX = Math.min(...rects.map(r => r.x));
    const minY = Math.min(...rects.map(r => r.y));
    const maxX = Math.max(...rects.map(r => r.x + r.w));

    const centerX = ((minX + maxX) / 2) * container.offsetWidth;
    const topY = minY * container.offsetHeight;

    // If annotation is near the top of the page, show toolbar below instead
    const showBelow = minY < 0.08;
    const maxY = Math.max(...rects.map(r => r.y + r.h));
    const bottomY = maxY * container.offsetHeight;

    return (
        <div
            className="absolute z-40 pointer-events-auto"
            style={{
                left: `${centerX}px`,
                top: showBelow ? `${bottomY + 8}px` : `${topY - 8}px`,
                transform: showBelow ? 'translateX(-50%)' : 'translate(-50%, -100%)',
            }}
            onClick={(e) => e.stopPropagation()}
        >
            <div className="bg-white border border-gray-200 rounded-lg shadow-lg px-2 py-1.5 flex items-center gap-1">
                {/* Color swatches */}
                {COLOR_PRESETS.map(({ color, label }) => (
                    <button
                        key={color}
                        data-color={color}
                        title={label}
                        className="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-transform hover:scale-110"
                        style={{
                            backgroundColor: color,
                            borderColor: annotation.color === color ? '#000' : 'transparent',
                        }}
                        onClick={() => handleColorChange(color)}
                    >
                        {annotation.color === color && (
                            <Check className="h-3 w-3 text-white drop-shadow-[0_0_1px_rgba(0,0,0,0.8)]" />
                        )}
                    </button>
                ))}

                {annotation.type !== 'note' && (
                    <>
                        <div className="w-px h-4 bg-border mx-0.5" />
                        <button
                            title={annotation.note_content ? 'Edit note' : 'Add note'}
                            className="w-6 h-6 rounded flex items-center justify-center hover:bg-muted transition-colors"
                            onClick={onEditNote}
                        >
                            <StickyNote className={`h-3.5 w-3.5 ${annotation.note_content ? 'text-amber-500' : 'text-muted-foreground'}`} />
                        </button>
                    </>
                )}
            </div>
        </div>
    );
};
