import { useState, useCallback, useEffect, useRef } from 'react';

type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

interface Rect {
    x: number;
    y: number;
    w: number;
    h: number;
}

interface DragPosition {
    clientX: number;
    clientY: number;
}

const MIN_SIZE = 0.02;

export function useAnnotationDrag(containerRef: React.RefObject<HTMLDivElement>) {
    const [resizeState, setResizeState] = useState<{
        handleId: HandleId;
        startPos: { x: number; y: number };
        startRect: Rect;
    } | null>(null);

    const [moveState, setMoveState] = useState<{
        startPos: { x: number; y: number };
        startRects: Rect[];
    } | null>(null);

    const [previewRect, setPreviewRect] = useState<Rect | null>(null);
    const [previewRects, setPreviewRects] = useState<Rect[] | null>(null);

    // Refs to access latest state in document listeners without re-registering
    const resizeRef = useRef(resizeState);
    const moveRef = useRef(moveState);
    useEffect(() => { resizeRef.current = resizeState; });
    useEffect(() => { moveRef.current = moveState; });

    const isDragging = resizeState !== null || moveState !== null;

    const getContainerDims = useCallback(() => {
        if (!containerRef.current) return null;
        const r = containerRef.current.getBoundingClientRect();
        return { left: r.left, top: r.top, width: r.width, height: r.height };
    }, [containerRef]);

    // Document-level mousemove handler
    const handleDocumentMouseMove = useCallback((e: MouseEvent) => {
        const dims = getContainerDims();
        if (!dims) return;

        const currentResize = resizeRef.current;
        const currentMove = moveRef.current;

        if (currentResize) {
            const dx = (e.clientX - currentResize.startPos.x) / dims.width;
            const dy = (e.clientY - currentResize.startPos.y) / dims.height;
            const { handleId, startRect } = currentResize;
            let { x, y, w, h } = startRect;

            if (handleId.includes('w')) { x += dx; w -= dx; }
            if (handleId.includes('e')) { w += dx; }
            if (handleId.includes('n')) { y += dy; h -= dy; }
            if (handleId.includes('s')) { h += dy; }

            w = Math.max(MIN_SIZE, w);
            h = Math.max(MIN_SIZE, h);
            if (handleId.includes('w')) x = Math.min(x, startRect.x + startRect.w - MIN_SIZE);
            if (handleId.includes('n')) y = Math.min(y, startRect.y + startRect.h - MIN_SIZE);

            x = Math.max(0, Math.min(x, 1 - MIN_SIZE));
            y = Math.max(0, Math.min(y, 1 - MIN_SIZE));

            setPreviewRect({ x, y, w, h });
        }

        if (currentMove) {
            const dx = (e.clientX - currentMove.startPos.x) / dims.width;
            const dy = (e.clientY - currentMove.startPos.y) / dims.height;

            const moved = currentMove.startRects.map(r => ({
                x: Math.max(0, Math.min(r.x + dx, 1 - r.w)),
                y: Math.max(0, Math.min(r.y + dy, 1 - r.h)),
                w: r.w,
                h: r.h,
            }));

            setPreviewRects(moved);
        }
    }, [getContainerDims]);

    // Callback ref for drag-end that the component can register
    const onDragEndCallbackRef = useRef<(() => void) | null>(null);

    // Register/unregister document listeners when dragging starts/stops
    useEffect(() => {
        if (!isDragging) return;

        document.addEventListener('mousemove', handleDocumentMouseMove);

        // Auto-end drag on document mouseup (prevents stuck drags when mouse
        // is released outside an annotation element or even outside the window)
        const handleMouseUp = () => {
            onDragEndCallbackRef.current?.();
        };
        document.addEventListener('mouseup', handleMouseUp);

        return () => {
            document.removeEventListener('mousemove', handleDocumentMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isDragging, handleDocumentMouseMove]);

    const startResize = useCallback((
        handleId: HandleId,
        e: DragPosition,
        rect: Rect,
    ) => {
        setResizeState({ handleId, startPos: { x: e.clientX, y: e.clientY }, startRect: rect });
        setPreviewRect(rect);
    }, []);

    const startMove = useCallback((e: DragPosition, rects: Rect[]) => {
        setMoveState({ startPos: { x: e.clientX, y: e.clientY }, startRects: rects });
        setPreviewRects(rects);
    }, []);

    const onDragEnd = useCallback((): { type: 'resize'; rect: Rect } | { type: 'move'; rects: Rect[] } | null => {
        let result = null;

        if (resizeState && previewRect) {
            result = { type: 'resize' as const, rect: previewRect };
        }

        if (moveState && previewRects) {
            result = { type: 'move' as const, rects: previewRects };
        }

        setResizeState(null);
        setMoveState(null);
        setPreviewRect(null);
        setPreviewRects(null);

        return result;
    }, [resizeState, moveState, previewRect, previewRects]);

    return {
        isDragging,
        previewRect,
        previewRects,
        startResize,
        startMove,
        onDragEnd,
        onDragEndCallbackRef,
    };
}
