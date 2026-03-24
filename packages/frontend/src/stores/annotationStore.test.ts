import { describe, it, expect, beforeEach } from 'vitest'
import { useAnnotationStore } from './annotationStore'

describe('annotationStore', () => {
  beforeEach(() => {
    // Reset store to defaults
    useAnnotationStore.setState({
      isDrawingRect: false,
      selectedSetId: null,
      hiddenSetIds: new Set<string>(),
      selectedAnnotationId: null,
      isSidebarOpen: true,
      sidebarGroupBy: 'page',
      contextMenu: null,
    })
  })

  describe('isDrawingRect', () => {
    it('defaults to false', () => {
      expect(useAnnotationStore.getState().isDrawingRect).toBe(false)
    })

    it('can be toggled on', () => {
      useAnnotationStore.getState().setIsDrawingRect(true)
      expect(useAnnotationStore.getState().isDrawingRect).toBe(true)
    })

    it('clears selectedAnnotationId when entering draw mode', () => {
      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')
      useAnnotationStore.getState().setIsDrawingRect(true)
      expect(useAnnotationStore.getState().selectedAnnotationId).toBeNull()
    })
  })

  describe('sidebarGroupBy', () => {
    it('defaults to page', () => {
      expect(useAnnotationStore.getState().sidebarGroupBy).toBe('page')
    })

    it('can be set to type', () => {
      useAnnotationStore.getState().setSidebarGroupBy('type')
      expect(useAnnotationStore.getState().sidebarGroupBy).toBe('type')
    })
  })

  describe('contextMenu', () => {
    it('defaults to null', () => {
      expect(useAnnotationStore.getState().contextMenu).toBeNull()
    })

    it('can be set with position and annotationId', () => {
      useAnnotationStore.getState().setContextMenu({ x: 100, y: 200, annotationId: 'ann-1' })
      expect(useAnnotationStore.getState().contextMenu).toEqual({ x: 100, y: 200, annotationId: 'ann-1' })
    })

    it('can be cleared', () => {
      useAnnotationStore.getState().setContextMenu({ x: 100, y: 200, annotationId: 'ann-1' })
      useAnnotationStore.getState().setContextMenu(null)
      expect(useAnnotationStore.getState().contextMenu).toBeNull()
    })
  })

  describe('setSelectedSetId', () => {
    it('clears selectedAnnotationId and contextMenu when switching sets', () => {
      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')
      useAnnotationStore.getState().setContextMenu({ x: 100, y: 200, annotationId: 'ann-1' })
      useAnnotationStore.getState().setSelectedSetId('set-2')
      expect(useAnnotationStore.getState().selectedAnnotationId).toBeNull()
      expect(useAnnotationStore.getState().contextMenu).toBeNull()
    })
  })
})
