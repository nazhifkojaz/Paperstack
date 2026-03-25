/**
 * Tests for AnnotationOverlay component.
 * Focus on coordinate mapping logic.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { AnnotationOverlay } from './AnnotationOverlay'
import { useAnnotationStore } from '@/stores/annotationStore'
import * as annotationsApi from '@/api/annotations'

const MOCK_SET = { id: 'set-1', name: 'Test', color: '#FF0000', pdf_id: 'pdf-1', user_id: 'user-1', created_at: '', updated_at: '' }

// Mock the API hooks
vi.mock('@/api/annotations', () => ({
  useAnnotationSets: vi.fn(() => ({ data: [MOCK_SET] })),
  useMultiSetAnnotations: vi.fn(() => ({ data: [], isLoading: false })),
  useAnnotations: vi.fn(() => ({ data: [] })),
  useCreateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useDeleteAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

describe('AnnotationOverlay', () => {
  beforeEach(() => {
    // Reset annotation store - use new interaction model
    useAnnotationStore.getState().setSelectedSetId('set-1')
    useAnnotationStore.getState().setIsDrawingRect(false)

    // Mock API defaults
    vi.mocked(annotationsApi.useAnnotationSets).mockReturnValue({ data: [MOCK_SET] } as any)
    vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({ data: [], isLoading: false })
    vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({
      mutate: vi.fn(),
    } as any)
    vi.mocked(annotationsApi.useUpdateAnnotation).mockReturnValue({
      mutate: vi.fn(),
    } as any)
  })

  describe('coordinate normalization', () => {
    it('normalizes click coordinates to 0-1 range when drawing rect', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({
        mutate: createMock,
      } as any)

      useAnnotationStore.getState().setIsDrawingRect(true)

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(overlay).toBeTruthy()

      // Mock the container dimensions
      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      // Simulate drawing a rectangle from (400, 500) to (600, 700)
      fireEvent.mouseDown(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseMove(overlay, { clientX: 600, clientY: 700 })
      fireEvent.mouseUp(overlay)

      // Expected: x = 400/800 = 0.5, y = 500/1000 = 0.5
      // w = |600-400|/800 = 0.25, h = |700-500|/1000 = 0.2
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          set_id: 'set-1',
          page_number: 1,
          type: 'rect',
          color: '#FF0000',
          rects: expect.arrayContaining([
            expect.objectContaining({
              x: 0.5,
              y: 0.5,
              w: 0.25,
              h: expect.closeTo(0.2, 5),
            }),
          ]),
        })
      )
    })

    it('handles reverse drag (negative width/height)', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({
        mutate: createMock,
      } as any)

      useAnnotationStore.getState().setIsDrawingRect(true)

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      // Drag from bottom-right to top-left (reverse)
      fireEvent.mouseDown(overlay, { clientX: 600, clientY: 700 })
      fireEvent.mouseMove(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseUp(overlay)

      // Should normalize to positive width/height with correct x,y
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          set_id: 'set-1',
          page_number: 1,
          type: 'rect',
          color: '#FF0000',
          rects: expect.arrayContaining([
            expect.objectContaining({
              x: 0.5,
              y: 0.5,
              w: 0.25,
              h: expect.closeTo(0.2, 5),
            }),
          ]),
        })
      )
    })

    it('ignores very small rectangles', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({
        mutate: createMock,
      } as any)

      useAnnotationStore.getState().setIsDrawingRect(true)

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      // Drag only a few pixels (resulting in < 0.01 normalized size)
      fireEvent.mouseDown(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseMove(overlay, { clientX: 405, clientY: 505 })
      fireEvent.mouseUp(overlay)

      // Should not create annotation for tiny rectangles
      expect(createMock).not.toHaveBeenCalled()
    })
  })

  describe('new interaction model', () => {
    it('overlay container is pointer-events-none by default', () => {
      useAnnotationStore.setState({ isDrawingRect: false, selectedSetId: 'set-1' })

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(overlay?.classList.contains('pointer-events-none')).toBe(true)
    })

    it('overlay container is pointer-events-auto when drawing rect', () => {
      useAnnotationStore.setState({ isDrawingRect: true, selectedSetId: 'set-1' })

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(overlay?.classList.contains('pointer-events-auto')).toBe(true)
      expect(overlay?.classList.contains('cursor-crosshair')).toBe(true)
    })

    it('annotation <g> elements have pointer-events all attribute', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      useAnnotationStore.setState({ selectedSetId: 'set-1' })

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const g = container.querySelector('g')
      expect(g?.getAttribute('pointer-events')).toBe('all')
    })

    it('fires onContextMenu and sets store contextMenu on right-click annotation', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      useAnnotationStore.setState({ selectedSetId: 'set-1' })

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const g = container.querySelector('g')!
      fireEvent.contextMenu(g, { clientX: 200, clientY: 300 })

      const { contextMenu, selectedAnnotationId } = useAnnotationStore.getState()
      expect(contextMenu).toEqual({ x: 200, y: 300, annotationId: 'ann-1' })
      expect(selectedAnnotationId).toBe('ann-1')
    })

    it('clears selection when clicking overlay background', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      fireEvent.click(overlay)

      expect(useAnnotationStore.getState().selectedAnnotationId).toBeNull()
    })

    it('does not draw when not in drawing mode', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({
        mutate: createMock,
      } as any)

      useAnnotationStore.getState().setIsDrawingRect(false)

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      fireEvent.mouseDown(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseUp(overlay)

      expect(createMock).not.toHaveBeenCalled()
    })
  })

  describe('annotation rendering', () => {
    it('filters annotations by page number', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'highlight', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FFFF00' },
        { id: 'ann-2', page_number: 2, type: 'highlight', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FFFF00' },
        { id: 'ann-3', page_number: 1, type: 'rect', rects: [{ x: 0.5, y: 0.5, w: 0.1, h: 0.1 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      // Should render 2 annotations (page 1 only)
      const groups = container.querySelectorAll('g')
      expect(groups.length).toBe(2)
    })

    it('highlights selected annotation', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      // Check that annotation is rendered
      const svg = container.querySelector('svg')
      expect(svg).toBeTruthy()

      // Check that a group for the annotation exists
      const groups = svg?.querySelectorAll('g')
      expect(groups?.length).toBe(1)

      // The rect should be rendered - just check it exists in the DOM
      const rect = svg?.querySelector('rect')
      expect(rect).toBeTruthy()
    })
  })

  describe('toolbar rendering', () => {
    it('renders toolbar when annotation is selected', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      // Toolbar should render when annotation is selected (no activeTool check needed)
      const svg = container.querySelector('svg')
      expect(svg).toBeTruthy()
      // The presence of resize handles indicates toolbar/rendering logic is active
      const handles = svg?.querySelectorAll('rect[stroke="#3b82f6"]')
      expect(handles?.length).toBeGreaterThan(0)
    })

    it('does not render toolbar for annotation on different page (cross-page guard)', () => {
      const mockAnnotations = [
        { id: 'ann-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
        { id: 'ann-2', page_number: 2, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000' },
      ]

      vi.mocked(annotationsApi.useMultiSetAnnotations).mockReturnValue({
        data: mockAnnotations as any,
        isLoading: false,
      })

      // Select annotation on page 2
      useAnnotationStore.getState().setSelectedAnnotationId('ann-2')

      // Render overlay for page 1
      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      // Toolbar should NOT render because selected annotation is on a different page
      // The implementation uses pageAnnotations.find() which would return undefined
      // Verify no toolbar-related elements (e.g., delete button title) appear
      expect(screen.queryByTitle(/delete/i)).not.toBeInTheDocument()
    })
  })

  describe('null selected set', () => {
    it('returns null when no set is selected and no visible sets', () => {
      vi.mocked(annotationsApi.useAnnotationSets).mockReturnValue({ data: [] } as any)
      useAnnotationStore.getState().setSelectedSetId(null)

      const { container } = render(
        <AnnotationOverlay pageNumber={1} pdfId="pdf-1" />
      )

      expect(container.firstChild).toBeNull()
    })
  })
})
