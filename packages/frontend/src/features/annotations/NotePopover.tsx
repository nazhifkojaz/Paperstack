import { useState, useEffect, useRef, useMemo } from 'react';
import Markdown from 'react-markdown';
import { useUpdateAnnotation, type Annotation } from '@/api/annotations';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Save, Pencil, Loader2, Sparkles } from 'lucide-react';

const PREFERRED_CARD_WIDTH = 384;
const CARD_MAX_HEIGHT = 420;
const EDGE_MARGIN = 8;

interface NotePopoverProps {
    annotation: Annotation;
    containerDims: { width: number; height: number } | null;
    onClose: () => void;
    isExplaining?: boolean;
    explainStatusMessage?: string;
}

function parseAiHeader(content: string): { isAi: boolean; header?: string; body: string } {
    const trimmed = content.trim();
    const match = trimmed.match(/^\[AI Explanation\s*—\s*([^\]]+)\]\s*(.*)$/s);
    if (match) {
        return { isAi: true, header: match[1].trim(), body: match[2].trim() };
    }
    return { isAi: false, body: trimmed };
}

export const NotePopover = ({ annotation, containerDims, onClose, isExplaining, explainStatusMessage }: NotePopoverProps) => {
    const [content, setContent] = useState(annotation.note_content || '');
    const [isEditing, setIsEditing] = useState(!annotation.note_content);
    const prevIsExplainingRef = useRef(isExplaining ?? false);

    // Sync state only when isExplaining transitions true → false (explain just completed)
    /* eslint-disable react-hooks/set-state-in-effect -- Sync after explain completes */
    useEffect(() => {
        if (prevIsExplainingRef.current && !isExplaining && annotation.note_content) {
            setContent(annotation.note_content);
            setIsEditing(false);
        }
        prevIsExplainingRef.current = isExplaining ?? false;
    }, [isExplaining, annotation.note_content]);
    /* eslint-enable react-hooks/set-state-in-effect */

    const { mutate: updateAnnotation } = useUpdateAnnotation();
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const popoverRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (isEditing) {
            textareaRef.current?.focus();
        }
    }, [isEditing]);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
                onClose();
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [onClose]);

    const handleSave = () => {
        updateAnnotation({
            id: annotation.id,
            data: { note_content: content },
        });
        onClose();
    };

    const handleCancel = () => {
        setContent(annotation.note_content || '');
        if (annotation.note_content) {
            setIsEditing(false);
        } else {
            onClose();
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            onClose();
        }
    };

    const parsedContent = useMemo(() => parseAiHeader(content), [content]);

    if (!containerDims || !annotation.rects[0]) return null;

    const rect = annotation.rects[0];
    const centerX = (rect.x + rect.w / 2) * containerDims.width;

    // Responsive width — never overflow the container
    const cardWidth = Math.min(PREFERRED_CARD_WIDTH, containerDims.width - EDGE_MARGIN * 2);

    // Horizontal positioning: center by default, clamp to edges
    const halfWidth = cardWidth / 2;
    let adjustedLeft: number;
    let horizontalTransform: string;

    if (centerX + halfWidth > containerDims.width - EDGE_MARGIN) {
        adjustedLeft = containerDims.width - cardWidth - EDGE_MARGIN;
        horizontalTransform = 'none';
    } else if (centerX - halfWidth < EDGE_MARGIN) {
        adjustedLeft = EDGE_MARGIN;
        horizontalTransform = 'none';
    } else {
        adjustedLeft = centerX;
        horizontalTransform = 'translateX(-50%)';
    }

    // Vertical positioning: flip above if near bottom and there's room above
    const annotationBottomY = (rect.y + rect.h) * containerDims.height;
    const annotationTopY = rect.y * containerDims.height;
    const spaceBelow = containerDims.height - annotationBottomY;
    const showAbove = spaceBelow < CARD_MAX_HEIGHT + 12 && annotationTopY > CARD_MAX_HEIGHT * 0.4;

    const topY = showAbove ? annotationTopY - 8 : annotationBottomY + 8;
    const verticalTransform = showAbove ? 'translateY(-100%)' : 'none';

    const isAiContent = parsedContent.isAi && !isEditing && !isExplaining;

    return (
        <div
            ref={popoverRef}
            className="absolute z-50 pointer-events-auto"
            style={{
                left: `${adjustedLeft}px`,
                top: `${topY}px`,
                transform: `${horizontalTransform} ${verticalTransform}`.trim(),
            }}
            onClick={(e) => e.stopPropagation()}
        >
            <div
                className={`rounded-xl shadow-2xl border flex flex-col ${
                    isAiContent
                        ? 'bg-violet-50/95 border-violet-200'
                        : 'bg-white border-gray-200'
                }`}
                style={{ width: `${cardWidth}px`, maxHeight: `${CARD_MAX_HEIGHT}px` }}
                data-testid="note-popover-card"
            >
                {/* Scrollable content */}
                <div className="flex-1 min-h-0 overflow-y-auto">
                    {isExplaining ? (
                        <div className="p-4 space-y-3">
                            <div className="flex items-center gap-2">
                                <Loader2 className="h-4 w-4 text-violet-600 animate-spin" />
                                <span className="text-sm text-gray-600 font-medium">
                                    {explainStatusMessage || 'Generating explanation…'}
                                </span>
                            </div>
                            <div className="space-y-2">
                                {[0.95, 0.8, 0.6, 0.85].map((w, i) => (
                                    <div
                                        key={i}
                                        className="h-3 bg-gray-200 rounded animate-pulse"
                                        style={{ width: `${w * 100}%` }}
                                    />
                                ))}
                            </div>
                        </div>
                    ) : isEditing ? (
                        <div className="p-3">
                            <Textarea
                                ref={textareaRef}
                                placeholder="Add a note…"
                                value={content}
                                onChange={(e) => setContent(e.target.value)}
                                onKeyDown={handleKeyDown}
                                className="min-h-[100px] resize-none text-sm border-0 focus-visible:ring-1 focus-visible:ring-violet-400 bg-transparent shadow-none"
                            />
                        </div>
                    ) : (
                        <div className="p-4">
                            {isAiContent && (
                                <div className="flex items-center gap-2 mb-3 pb-2 border-b border-violet-100/80">
                                    <Sparkles className="h-3.5 w-3.5 text-violet-600 shrink-0" />
                                    <Badge
                                        variant="outline"
                                        className="text-xs font-medium text-violet-700 border-violet-200 bg-violet-50 hover:bg-violet-100"
                                    >
                                        AI Explanation
                                    </Badge>
                                    {parsedContent.header && (
                                        <span className="text-xs text-violet-400 ml-auto tabular-nums shrink-0">
                                            {parsedContent.header}
                                        </span>
                                    )}
                                </div>
                            )}
                            <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 text-gray-800 leading-relaxed">
                                <Markdown>{parsedContent.body}</Markdown>
                            </div>
                        </div>
                    )}
                </div>

                {/* Sticky footer */}
                <div
                    className={`shrink-0 border-t px-3 py-2.5 flex justify-end gap-2 ${
                        isAiContent
                            ? 'border-violet-100 bg-violet-50/60'
                            : 'border-gray-100 bg-white/80 backdrop-blur-sm'
                    }`}
                >
                    {isExplaining ? (
                        <Button size="sm" variant="ghost" onClick={onClose}>
                            Cancel
                        </Button>
                    ) : isEditing ? (
                        <>
                            <Button size="sm" variant="ghost" onClick={handleCancel}>
                                Cancel
                            </Button>
                            <Button size="sm" onClick={handleSave}>
                                <Save className="h-3 w-3 mr-1" />
                                Save
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button size="sm" variant="ghost" onClick={onClose}>
                                Close
                            </Button>
                            <Button size="sm" onClick={() => setIsEditing(true)}>
                                <Pencil className="h-3 w-3 mr-1" />
                                Edit Note
                            </Button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};
