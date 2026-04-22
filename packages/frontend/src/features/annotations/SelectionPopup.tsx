import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useParams } from 'react-router-dom';
import { useCreateAnnotation, useAnnotationSets } from '@/api/annotations';
import { useAnnotationStore } from '@/stores/annotationStore';
import { Button } from '@/components/ui/button';
import { Highlighter } from 'lucide-react';

interface SelectionPopupProps {
    selectionRect: { x: number; y: number; width: number; height: number };
    normalizedRects: Array<{ x: number; y: number; w: number; h: number }>;
    selectedText: string;
    pageNumber: number;
    onDismiss: () => void;
}

export const SelectionPopup = ({
    selectionRect,
    normalizedRects,
    selectedText,
    pageNumber,
    onDismiss,
}: SelectionPopupProps) => {
    const { pdfId = '' } = useParams<{ pdfId: string }>();
    const selectedSetId = useAnnotationStore(s => s.selectedSetId);
    const { data: sets } = useAnnotationSets(pdfId);
    const { mutate: createAnnotation } = useCreateAnnotation();

    const popupRef = useRef<HTMLDivElement>(null);

    // Find the active set color
    const activeSet = sets?.find((s) => s.id === selectedSetId);
    const setColor = activeSet?.color ?? '#FFFF00';

    // Close on click outside (but NOT immediately after text selection)
    useEffect(() => {
        let mouseDownTime = 0;

        const handleMouseDown = () => {
            mouseDownTime = Date.now();
        };

        const handleClick = (e: MouseEvent) => {
            // Only dismiss if:
            // 1. Click is outside the popup
            // 2. Enough time has passed since mousedown (not a text selection)
            // 3. The click target hasn't changed (it's the same interaction)
            const timeSinceMouseDown = Date.now() - mouseDownTime;

            if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
                // Only dismiss if this was a quick click (not a text selection drag)
                // Text selections typically take > 200ms
                if (timeSinceMouseDown < 200) {
                    onDismiss();
                }
            }
        };

        document.addEventListener('mousedown', handleMouseDown, { capture: true });
        document.addEventListener('click', handleClick, { capture: true });
        const listenerOpts: EventListenerOptions = { capture: true };
        return () => {
            document.removeEventListener('mousedown', handleMouseDown, listenerOpts);
            document.removeEventListener('click', handleClick, listenerOpts);
        };
    }, [onDismiss]);

    const handleHighlight = () => {
        if (!selectedSetId) return;

        createAnnotation(
            {
                set_id: selectedSetId,
                page_number: pageNumber,
                type: 'highlight',
                rects: normalizedRects,
                selected_text: selectedText,
                color: setColor,
            },
            {
                onSuccess: () => {
                    onDismiss();
                },
            }
        );
    };

    // Position popup centered above selection, flip below if near top
    const popupWidth = 200; // Approximate width
    const left = Math.max(8, Math.min(selectionRect.x + selectionRect.width / 2 - popupWidth / 2, window.innerWidth - popupWidth - 8));
    const top = selectionRect.y < 100 ? selectionRect.y + selectionRect.height + 8 : selectionRect.y - 48;

    // No set selected - show hint
    if (!selectedSetId) {
        return createPortal(
            <div
                ref={popupRef}
                className="fixed z-[9999] pointer-events-auto bg-white border border-gray-300 rounded-lg shadow-xl px-3 py-2 text-sm text-gray-700"
                style={{ left: `${left}px`, top: `${top}px` }}
            >
                Create an annotation set first
            </div>,
            document.body
        );
    }

    return createPortal(
        <div
            ref={popupRef}
            className="fixed z-[9999] pointer-events-auto bg-white border border-gray-300 rounded-lg shadow-xl flex items-center gap-1 p-1"
            style={{ left: `${left}px`, top: `${top}px` }}
        >
            <Button
                size="sm"
                variant="ghost"
                className="h-8 px-2 gap-1.5"
                onClick={handleHighlight}
            >
                <Highlighter className="h-3.5 w-3.5" style={{ color: setColor }} />
                Highlight
            </Button>
        </div>,
        document.body
    );
};
