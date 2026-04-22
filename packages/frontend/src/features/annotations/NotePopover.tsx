import { useState, useEffect, useRef } from 'react';
import Markdown from 'react-markdown';
import { useUpdateAnnotation, type Annotation } from '@/api/annotations';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Save, Pencil, Loader2 } from 'lucide-react';

interface NotePopoverProps {
    annotation: Annotation;
    containerDims: { width: number; height: number } | null;
    onClose: () => void;
    isExplaining?: boolean;
    explainStatusMessage?: string;
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

    if (!containerDims || !annotation.rects[0]) return null;

    const rect = annotation.rects[0];
    const centerX = (rect.x + rect.w / 2) * containerDims.width;
    const topY = (rect.y + rect.h) * containerDims.height;

    // Edge detection: if note is near right edge, align to right side
    const popoverWidth = 256; // w-64 = 16rem = 256px
    const shouldAlignRight = centerX + popoverWidth / 2 > containerDims.width;
    const adjustedLeft = shouldAlignRight
        ? containerDims.width - popoverWidth - 8
        : centerX;

    return (
        <div
            ref={popoverRef}
            className="absolute z-40 pointer-events-auto"
            style={{
                left: `${adjustedLeft}px`,
                top: `${topY + 8}px`,
                transform: shouldAlignRight ? 'none' : 'translateX(-50%)',
            }}
            onClick={(e) => e.stopPropagation()}
        >
            <div className="bg-white border border-gray-300 rounded-lg shadow-xl p-3 w-64">
                {isExplaining ? (
                    <>
                        <div className="flex items-center gap-2 mb-3">
                            <Loader2 className="h-3 w-3 text-violet-600 animate-spin" />
                            <span className="text-xs text-gray-500">
                                {explainStatusMessage || 'Generating explanation...'}
                            </span>
                        </div>
                        <div className="space-y-2 min-h-[80px]">
                            <div className="h-3 bg-gray-200 rounded animate-pulse w-full" />
                            <div className="h-3 bg-gray-200 rounded animate-pulse w-4/5" />
                            <div className="h-3 bg-gray-200 rounded animate-pulse w-3/5" />
                            <div className="h-3 bg-gray-200 rounded animate-pulse w-4/5" />
                        </div>
                        <div className="flex justify-end mt-2">
                            <Button size="sm" variant="ghost" onClick={onClose}>
                                Cancel
                            </Button>
                        </div>
                    </>
                ) : isEditing ? (
                    <>
                        <Textarea
                            ref={textareaRef}
                            placeholder="Add a note..."
                            value={content}
                            onChange={(e) => setContent(e.target.value)}
                            onKeyDown={handleKeyDown}
                            className="min-h-[80px] resize-none text-sm"
                        />
                        <div className="flex justify-end gap-2 mt-2">
                            <Button size="sm" variant="ghost" onClick={handleCancel}>
                                Cancel
                            </Button>
                            <Button size="sm" onClick={handleSave}>
                                <Save className="h-3 w-3 mr-1" />
                                Save
                            </Button>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="prose prose-sm max-w-none min-h-[80px] prose-p:my-1 prose-ul:my-1 prose-li:my-0 text-gray-800">
                            <Markdown>{content}</Markdown>
                        </div>
                        <div className="flex justify-end gap-2 mt-2">
                            <Button size="sm" variant="ghost" onClick={onClose}>
                                Close
                            </Button>
                            <Button size="sm" onClick={() => setIsEditing(true)}>
                                <Pencil className="h-3 w-3 mr-1" />
                                Edit Note
                            </Button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};
