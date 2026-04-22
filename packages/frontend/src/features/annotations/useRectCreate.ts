import { useState, useCallback, RefObject } from 'react';

export interface Rect {
    x: number;
    y: number;
    w: number;
    h: number;
}

interface UseRectCreateOptions {
    containerRef: RefObject<HTMLDivElement | null>;
    isDrawingRect: boolean;
    selectedSetId: string | null;
    onCreate: (rect: Rect) => void;
    onDrawingEnd?: () => void;
}

interface UseRectCreateReturn {
    /** Preview rect while dragging */
    previewRect: Rect | null;
    /** Mouse down handler */
    handleMouseDown: (e: React.MouseEvent) => void;
    /** Mouse move handler */
    handleMouseMove: (e: React.MouseEvent) => void;
    /** Mouse up handler */
    handleMouseUp: () => void;
    /** Mouse leave handler */
    handleMouseLeave: () => void;
    /** Cancel current drawing */
    cancel: () => void;
}

/**
 * Hook for managing drag-to-create rectangle annotation workflow.
 *
 * Handles:
 * - Mouse down/move/up for drawing rectangles
 * - Coordinate normalization (0-1 range)
 * - Minimum size validation
 * - Auto-disable drawing mode after creation
 */
export function useRectCreate(options: UseRectCreateOptions): UseRectCreateReturn {
    const { containerRef, isDrawingRect, selectedSetId, onCreate, onDrawingEnd } = options;

    const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
    const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null);

    const getNormalizedCoordinates = useCallback((e: React.MouseEvent) => {
        if (!containerRef.current) return null;
        const rect = containerRef.current.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) / rect.width,
            y: (e.clientY - rect.top) / rect.height,
        };
    }, [containerRef]);

    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        // Only allow drawing when isDrawingRect is true and we have a selected set
        if (!isDrawingRect || !selectedSetId) return;
        const coords = getNormalizedCoordinates(e);
        if (coords) {
            setDragStart(coords);
            setDragCurrent(coords);
        }
    }, [isDrawingRect, selectedSetId, getNormalizedCoordinates]);

    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        if (!dragStart) return;
        const coords = getNormalizedCoordinates(e);
        if (coords) {
            setDragCurrent(coords);
        }
    }, [dragStart, getNormalizedCoordinates]);

    const handleMouseUp = useCallback(() => {
        if (!dragStart || !dragCurrent || !selectedSetId) {
            setDragStart(null);
            setDragCurrent(null);
            return;
        }

        const x = Math.min(dragStart.x, dragCurrent.x);
        const y = Math.min(dragStart.y, dragCurrent.y);
        const w = Math.abs(dragCurrent.x - dragStart.x);
        const h = Math.abs(dragCurrent.y - dragStart.y);

        // Minimum size threshold (0.01 = 1% of container)
        if (w > 0.01 && h > 0.01) {
            onCreate({ x, y, w, h });
            // Call onDrawingEnd callback (e.g., to disable drawing mode)
            onDrawingEnd?.();
        }

        setDragStart(null);
        setDragCurrent(null);
    }, [dragStart, dragCurrent, selectedSetId, onCreate, onDrawingEnd]);

    const handleMouseLeave = useCallback(() => {
        setDragStart(null);
        setDragCurrent(null);
    }, []);

    const cancel = useCallback(() => {
        setDragStart(null);
        setDragCurrent(null);
    }, []);

    // Compute preview rect
    let previewRect: Rect | null = null;
    if (dragStart && dragCurrent && isDrawingRect) {
        const x = Math.min(dragStart.x, dragCurrent.x);
        const y = Math.min(dragStart.y, dragCurrent.y);
        const w = Math.abs(dragCurrent.x - dragStart.x);
        const h = Math.abs(dragCurrent.y - dragStart.y);
        previewRect = { x, y, w, h };
    }

    return {
        previewRect,
        handleMouseDown,
        handleMouseMove,
        handleMouseUp,
        handleMouseLeave,
        cancel,
    };
}
