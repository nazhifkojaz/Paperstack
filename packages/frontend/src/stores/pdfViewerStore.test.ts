/**
 * Tests for pdfViewerStore.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { usePdfViewerStore } from './pdfViewerStore'

describe('pdfViewerStore', () => {
  beforeEach(() => {
    usePdfViewerStore.getState().reset()
  })

  describe('initial state', () => {
    it('has correct default values', () => {
      const state = usePdfViewerStore.getState()

      expect(state.currentPage).toBe(1)
      expect(state.totalPages).toBe(0)
      expect(state.zoom).toBe(1.0)
      expect(state.rotation).toBe(0)
    })
  })

  describe('setCurrentPage', () => {
    it('sets current page', () => {
      usePdfViewerStore.getState().setCurrentPage(5)

      expect(usePdfViewerStore.getState().currentPage).toBe(5)
    })
  })

  describe('setTotalPages', () => {
    it('sets total pages', () => {
      usePdfViewerStore.getState().setTotalPages(25)

      expect(usePdfViewerStore.getState().totalPages).toBe(25)
    })
  })

  describe('setZoom', () => {
    it('sets zoom to specific value', () => {
      usePdfViewerStore.getState().setZoom(2.5)

      expect(usePdfViewerStore.getState().zoom).toBe(2.5)
    })

    it('sets zoom using function', () => {
      usePdfViewerStore.getState().setZoom(1.0)
      usePdfViewerStore.getState().setZoom((prev) => prev * 2)

      expect(usePdfViewerStore.getState().zoom).toBe(2.0)
    })
  })

  describe('setRotation', () => {
    it('sets rotation to specific value', () => {
      usePdfViewerStore.getState().setRotation(90)

      expect(usePdfViewerStore.getState().rotation).toBe(90)
    })

    it('sets rotation using function', () => {
      usePdfViewerStore.getState().setRotation(0)
      usePdfViewerStore.getState().setRotation((prev) => prev + 90)

      expect(usePdfViewerStore.getState().rotation).toBe(90)
    })

    it('handles rotation wraparound', () => {
      usePdfViewerStore.getState().setRotation(270)
      usePdfViewerStore.getState().setRotation((prev) => (prev + 90) % 360)

      expect(usePdfViewerStore.getState().rotation).toBe(0)
    })
  })

  describe('reset', () => {
    it('resets to initial state', () => {
      usePdfViewerStore.getState().setCurrentPage(10)
      usePdfViewerStore.getState().setTotalPages(50)
      usePdfViewerStore.getState().setZoom(2.0)
      usePdfViewerStore.getState().setRotation(180)

      usePdfViewerStore.getState().reset()

      const state = usePdfViewerStore.getState()
      expect(state.currentPage).toBe(1)
      expect(state.totalPages).toBe(0)
      expect(state.zoom).toBe(1.0)
      expect(state.rotation).toBe(0)
    })
  })
})
