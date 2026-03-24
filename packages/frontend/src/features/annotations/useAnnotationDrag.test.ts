import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAnnotationDrag } from './useAnnotationDrag'

describe('useAnnotationDrag', () => {
  let containerRef: React.RefObject<HTMLDivElement>
  let addSpy: ReturnType<typeof vi.spyOn>
  let removeSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    const div = document.createElement('div')
    Object.defineProperty(div, 'getBoundingClientRect', {
      value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
    })
    containerRef = { current: div }
    addSpy = vi.spyOn(document, 'addEventListener')
    removeSpy = vi.spyOn(document, 'removeEventListener')
  })

  afterEach(() => {
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('registers document listeners on startResize', () => {
    const { result } = renderHook(() => useAnnotationDrag(containerRef))

    act(() => {
      result.current.startResize('se', { clientX: 400, clientY: 500 }, { x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    })

    expect(addSpy).toHaveBeenCalledWith('mousemove', expect.any(Function))
    expect(addSpy).toHaveBeenCalledWith('mouseup', expect.any(Function))
    expect(result.current.isDragging).toBe(true)
  })

  it('removes document listeners on drag end', () => {
    const { result } = renderHook(() => useAnnotationDrag(containerRef))

    act(() => {
      result.current.startResize('se', { clientX: 400, clientY: 500 }, { x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    })

    act(() => {
      result.current.onDragEnd()
    })

    expect(removeSpy).toHaveBeenCalledWith('mousemove', expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith('mouseup', expect.any(Function))
    expect(result.current.isDragging).toBe(false)
  })

  it('registers document listeners on startMove', () => {
    const { result } = renderHook(() => useAnnotationDrag(containerRef))

    act(() => {
      result.current.startMove({ clientX: 400, clientY: 500 }, [{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }])
    })

    expect(addSpy).toHaveBeenCalledWith('mousemove', expect.any(Function))
    expect(addSpy).toHaveBeenCalledWith('mouseup', expect.any(Function))
    expect(result.current.isDragging).toBe(true)
  })

  it('updates previewRect on document mousemove during resize', () => {
    const { result } = renderHook(() => useAnnotationDrag(containerRef))

    act(() => {
      result.current.startResize('se', { clientX: 400, clientY: 500 }, { x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    })

    // Simulate document mousemove
    act(() => {
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 500, clientY: 600 }))
    })

    expect(result.current.previewRect).not.toBeNull()
    // se handle: w and h should increase
    expect(result.current.previewRect!.w).toBeGreaterThan(0.2)
    expect(result.current.previewRect!.h).toBeGreaterThan(0.2)
  })

  it('returns result and cleans up on onDragEnd after resize', () => {
    const { result } = renderHook(() => useAnnotationDrag(containerRef))

    act(() => {
      result.current.startResize('se', { clientX: 400, clientY: 500 }, { x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    })

    let endResult: any
    act(() => {
      endResult = result.current.onDragEnd()
    })

    expect(endResult).toEqual({ type: 'resize', rect: expect.any(Object) })
    expect(result.current.isDragging).toBe(false)
    expect(result.current.previewRect).toBeNull()
  })
})
