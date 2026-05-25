/**
 * Tests for ViewerToolbar component (using new pdfViewerStore).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { ViewerToolbar } from './ViewerToolbar'
import { useNewPdfViewerStore } from '@/features/pdf-viewer/pdfViewerStore'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('@/stores/annotationStore', () => ({
  useAnnotationStore: () => ({
    isAnnotationSidebarOpen: true,
    toggleAnnotationSidebar: vi.fn(),
  }),
}))

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
    useNewPdfViewerStore.getState().reset()
    useNewPdfViewerStore.getState().setTotalPages(10)
    useNewPdfViewerStore.getState().setVisiblePage(5)
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
      useNewPdfViewerStore.getState().setVisiblePage(1)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const prevBtn = buttons.find(b => b.querySelector('.lucide-chevron-left'))

      expect(prevBtn?.closest('button')).toBeDisabled()
    })

    it('disables next button on last page', () => {
      useNewPdfViewerStore.getState().setVisiblePage(10)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const nextBtn = buttons.find(b => b.querySelector('.lucide-chevron-right'))

      expect(nextBtn?.closest('button')).toBeDisabled()
    })

    it('sets targetPage on next button click', () => {
      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const nextBtn = buttons.find(b => b.querySelector('.lucide-chevron-right'))

      fireEvent.click(nextBtn!)

      // jumpToPage sets targetPage, not visiblePage
      expect(useNewPdfViewerStore.getState().targetPage).toBe(6)
    })

    it('sets targetPage on prev button click', () => {
      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const prevBtn = buttons.find(b => b.querySelector('.lucide-chevron-left'))

      fireEvent.click(prevBtn!)

      expect(useNewPdfViewerStore.getState().targetPage).toBe(4)
    })

    it('sets targetPage on direct page input', () => {
      renderWithRouter(<ViewerToolbar />)

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '7' } })

      expect(useNewPdfViewerStore.getState().targetPage).toBe(7)
    })

    it('rejects invalid page input', () => {
      renderWithRouter(<ViewerToolbar />)

      const input = screen.getByRole('spinbutton')
      fireEvent.change(input, { target: { value: '999' } })

      // Should not update due to max validation
      expect(useNewPdfViewerStore.getState().targetPage).toBeNull()
    })
  })

  describe('zoom controls', () => {
    it('zooms in on click', () => {
      useNewPdfViewerStore.getState().setZoom(1.0)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomInBtn = buttons.find(b => b.querySelector('.lucide-zoom-in'))

      fireEvent.click(zoomInBtn!)

      expect(useNewPdfViewerStore.getState().zoom).toBe(1.25)
    })

    it('zooms out on click', () => {
      useNewPdfViewerStore.getState().setZoom(1.5)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomOutBtn = buttons.find(b => b.querySelector('.lucide-zoom-out'))

      fireEvent.click(zoomOutBtn!)

      expect(useNewPdfViewerStore.getState().zoom).toBe(1.25)
    })

    it('respects minimum zoom limit', () => {
      useNewPdfViewerStore.getState().setZoom(0.25)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomOutBtn = buttons.find(b => b.querySelector('.lucide-zoom-out'))

      fireEvent.click(zoomOutBtn!)

      expect(useNewPdfViewerStore.getState().zoom).toBe(0.25)
    })

    it('respects maximum zoom limit', () => {
      useNewPdfViewerStore.getState().setZoom(5.0)

      renderWithRouter(<ViewerToolbar />)

      const buttons = screen.getAllByRole('button')
      const zoomInBtn = buttons.find(b => b.querySelector('.lucide-zoom-in'))

      fireEvent.click(zoomInBtn!)

      expect(useNewPdfViewerStore.getState().zoom).toBe(5.0)
    })

    it('displays current zoom percentage', () => {
      useNewPdfViewerStore.getState().setZoom(1.5)

      renderWithRouter(<ViewerToolbar />)

      expect(screen.getByText('150%')).toBeTruthy()
    })
  })
})
