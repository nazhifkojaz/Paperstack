import { useEffect } from 'react';
import { useAnnotationStore } from '@/stores/annotationStore';

const EDITABLE_ELEMENTS = ['INPUT', 'TEXTAREA', 'SELECT'];

function isEditableElement(element: EventTarget | null): boolean {
    if (!element || !(element instanceof HTMLElement)) return false;

    if (EDITABLE_ELEMENTS.includes(element.tagName)) return true;

    if (element.isContentEditable) return true;

    return false;
}

export function useKeyboardShortcuts() {
    const { toggleAnnotationSidebar, setSelectedAnnotationId, setIsDrawingRect, setContextMenu } = useAnnotationStore();

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
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

                if (state.contextMenu) {
                    setContextMenu(null);
                    return;
                }

                if (state.isDrawingRect) {
                    setIsDrawingRect(false);
                    return;
                }

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
