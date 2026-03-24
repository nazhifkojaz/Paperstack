import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcuts } from './useKeyboardShortcuts'
import { useAnnotationStore } from '@/stores/annotationStore'

describe('useKeyboardShortcuts', () => {
  beforeEach(() => {
    useAnnotationStore.setState({
      isSidebarOpen: true,
      selectedAnnotationId: null,
      isDrawingRect: false,
      contextMenu: null,
    })
  })

  it('toggles sidebar on Ctrl+backslash', () => {
    renderHook(() => useKeyboardShortcuts())
    expect(useAnnotationStore.getState().isSidebarOpen).toBe(true)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: '\\', ctrlKey: true }))
    expect(useAnnotationStore.getState().isSidebarOpen).toBe(false)
  })

  it('clears selectedAnnotationId on Escape', () => {
    useAnnotationStore.setState({ selectedAnnotationId: 'ann-1' })
    renderHook(() => useKeyboardShortcuts())
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(useAnnotationStore.getState().selectedAnnotationId).toBeNull()
  })

  it('cancels isDrawingRect on Escape', () => {
    useAnnotationStore.setState({ isDrawingRect: true })
    renderHook(() => useKeyboardShortcuts())
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(useAnnotationStore.getState().isDrawingRect).toBe(false)
  })

  it('clears contextMenu on Escape', () => {
    useAnnotationStore.setState({ contextMenu: { x: 100, y: 200, annotationId: 'ann-1' } })
    renderHook(() => useKeyboardShortcuts())
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(useAnnotationStore.getState().contextMenu).toBeNull()
  })

  it('does not fire when a textarea is focused', () => {
    renderHook(() => useKeyboardShortcuts())
    const textarea = document.createElement('textarea')
    document.body.appendChild(textarea)
    textarea.focus()

    // Dispatch event on textarea so the event target is the textarea
    const event = new KeyboardEvent('keydown', { key: '\\', ctrlKey: true, bubbles: true })
    Object.defineProperty(event, 'target', { value: textarea, enumerable: true })
    textarea.dispatchEvent(event)

    expect(useAnnotationStore.getState().isSidebarOpen).toBe(true)
    document.body.removeChild(textarea)
  })
})
