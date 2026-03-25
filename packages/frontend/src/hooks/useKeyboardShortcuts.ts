import { useEffect } from 'react';
import { useAnnotationStore } from '@/stores/annotationStore';

const EDITABLE_ELEMENTS = ['INPUT', 'TEXTAREA', 'SELECT'];

function isEditableElement(element: EventTarget | null): boolean {
    if (!element || !(element instanceof HTMLElement)) return false;

    // Check for standard editable tags
    if (EDITABLE_ELEMENTS.includes(element.tagName)) return true;

    // Check for contentEditable
    if (element.isContentEditable) return true;

    return false;
}

export function useKeyboardShortcuts() {
    const { toggleAnnotationSidebar, setSelectedAnnotationId, setIsDrawingRect, setContextMenu } = useAnnotationStore();

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Skip if an editable element is focused
            if (isEditableElement(e.target)) return;

            // Ctrl+backslash (or Meta+backslash on Mac) toggles sidebar
            if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
                e.preventDefault();
                toggleAnnotationSidebar();
                return;
            }

            // Escape key: dismiss in priority order
            if (e.key === 'Escape') {
                const state = useAnnotationStore.getState();

                // Priority 1: Clear context menu
                if (state.contextMenu) {
                    setContextMenu(null);
                    return;
                }

                // Priority 2: Cancel drawing rectangle
                if (state.isDrawingRect) {
                    setIsDrawingRect(false);
                    return;
                }

                // Priority 3: Deselect annotation
                if (state.selectedAnnotationId) {
                    setSelectedAnnotationId(null);
                    return;
                }
            }
        };

        document.addEventListener('keydown', handleKeyDown);

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [toggleAnnotationSidebar, setSelectedAnnotationId, setIsDrawingRect, setContextMenu]);
}
