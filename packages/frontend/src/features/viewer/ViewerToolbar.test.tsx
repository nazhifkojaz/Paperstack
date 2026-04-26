/**
 * Tests for ViewerToolbar component.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { ViewerToolbar } from './ViewerToolbar'
import { usePdfViewerStore } from '@/stores/pdfViewerStore'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

// Mock annotation store
vi.mock('@/stores/annotationStore', () => ({
  useAnnotationStore: () => ({
    isAnnotationSidebarOpen: true,
    toggleAnnotationSidebar: vi.fn(),
  }),
}))

// Mock auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      accessToken: 'test-token',
      refreshToken: null,
      user: null,
      setAuth: vi.fn(),
      logout: vi.fn(),
    })),
  },
}))

describe('ViewerToolbar', () => {
  beforeEach(() => {
    usePdfViewerStore.getState().reset()
    usePdfViewerStore.getState().setTotalPages(10)
    usePdfViewerStore.getState().setCurrentPage(5)
  })

  const renderWithRouter = (component: React.ReactNode) => {
    return render(
      <MemoryRouter initialEntries={['/viewer/test-pdf-id']}>
        <Routes>
          <Route path="/viewer/:id" element={component} />
        </Routes>
      </MemoryRouter>
    )
  }

  describe('page navigation', () => {
    it('disables prev button on first page', () => {
      usePdfViewerStore.getState().setCurrentPage(1)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const prevBtn = buttons.find(b => b.querySelector('.lucide-chevron-left'))

      expect(prevBtn?.closest('button')).toBeDisabled()
    })

    it('disables next button on last page', () => {
      usePdfViewerStore.getState().setCurrentPage(10)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const nextBtn = buttons.find(b => b.querySelector('.lucide-chevron-right'))

      expect(nextBtn?.closest('button')).toBeDisabled()
    })

    it('increments page on next button click', () => {
      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const nextBtn = buttons.find(b => b.querySelector('.lucide-chevron-right'))

      fireEvent.click(nextBtn!)

      expect(usePdfViewerStore.getState().currentPage).toBe(6)
    })

    it('decrements page on prev button click', () => {
      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const prevBtn = buttons.find(b => b.querySelector('.lucide-chevron-left'))

      fireEvent.click(prevBtn!)

      expect(usePdfViewerStore.getState().currentPage).toBe(4)
    })

    it('accepts direct page input', () => {
      renderWithRouter(<ViewerToolbar />)

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '7' } })

      expect(usePdfViewerStore.getState().currentPage).toBe(7)
    })

    it('rejects invalid page input', () => {
      renderWithRouter(<ViewerToolbar />)

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '999' } })

      // Should not update due to max validation
      expect(usePdfViewerStore.getState().currentPage).toBeLessThanOrEqual(10)
    })
  })

  describe('zoom controls', () => {
    it('zooms in on click', () => {
      usePdfViewerStore.getState().setZoom(1.0)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomInBtn = buttons.find(b => b.querySelector('.lucide-zoom-in'))

      fireEvent.click(zoomInBtn!)

      expect(usePdfViewerStore.getState().zoom).toBe(1.25)
    })

    it('zooms out on click', () => {
      usePdfViewerStore.getState().setZoom(1.5)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomOutBtn = buttons.find(b => b.querySelector('.lucide-zoom-out'))

      fireEvent.click(zoomOutBtn!)

      expect(usePdfViewerStore.getState().zoom).toBe(1.25)
    })

    it('respects minimum zoom limit', () => {
      usePdfViewerStore.getState().setZoom(0.25)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomOutBtn = buttons.find(b => b.querySelector('.lucide-zoom-out'))

      fireEvent.click(zoomOutBtn!)

      expect(usePdfViewerStore.getState().zoom).toBe(0.25)
    })

    it('respects maximum zoom limit', () => {
      usePdfViewerStore.getState().setZoom(5.0)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomInBtn = buttons.find(b => b.querySelector('.lucide-zoom-in'))

      fireEvent.click(zoomInBtn!)

      expect(usePdfViewerStore.getState().zoom).toBe(5.0)
    })

    it('displays current zoom percentage', () => {
      usePdfViewerStore.getState().setZoom(1.5)

      renderWithRouter(<ViewerToolbar />)

      expect(screen.getByText('150%')).toBeTruthy()
    })
  })
})
