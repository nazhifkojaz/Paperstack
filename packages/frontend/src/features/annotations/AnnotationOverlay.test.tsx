/**
 * Tests for AnnotationOverlay component.
 * Focus on coordinate mapping logic.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { AnnotationOverlay } from './AnnotationOverlay'
import { AnnotationsContext, type AnnotationsContextValue } from './AnnotationsContext'
import { useAnnotationStore } from '@/stores/annotationStore'
import * as annotationsApi from '@/api/annotations'
import type { Annotation, AnnotationSet } from '@/api/annotations'

const MOCK_SET: AnnotationSet = { id: 'set-1', name: 'Test', color: '#FF0000', pdf_id: 'pdf-1', user_id: 'user-1', created_at: '', updated_at: '' }

// Mock the API hooks still used directly by AnnotationOverlay
vi.mock('@/api/annotations', () => ({
  useAnnotationSets: vi.fn(() => ({ data: [MOCK_SET] })),
  useMultiSetAnnotations: vi.fn(() => ({ data: [], isLoading: false })),
  useAnnotations: vi.fn(() => ({ data: [] })),
  useCreateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useDeleteAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

// ─── Context helpers ─────────────────────────────────────────────────────────

function buildAnnotationsContext(
  annotations: Annotation[] = [],
  sets: AnnotationSet[] = [MOCK_SET],
): AnnotationsContextValue {
  const annotationsByPage = new Map<number, Annotation[]>()
  for (const ann of annotations) {
    let list = annotationsByPage.get(ann.page_number)
    if (!list) { list = []; annotationsByPage.set(ann.page_number, list) }
    list.push(ann)
  }
  return { allSets: sets, visibleSetIds: sets.map(s => s.id), annotationsByPage }
}

function renderOverlay(
  pageNumber: number,
  contextValue: AnnotationsContextValue = buildAnnotationsContext(),
) {
  return render(
    <AnnotationsContext.Provider value={contextValue}>
      <AnnotationOverlay pageNumber={pageNumber} pdfId="pdf-1" />
    </AnnotationsContext.Provider>
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('AnnotationOverlay', () => {
  beforeEach(() => {
    useAnnotationStore.getState().setSelectedSetId('set-1')
    useAnnotationStore.getState().setIsDrawingRect(false)

    vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({ mutate: vi.fn() } as any)
    vi.mocked(annotationsApi.useUpdateAnnotation).mockReturnValue({ mutate: vi.fn() } as any)
  })

  describe('coordinate normalization', () => {
    it('normalizes click coordinates to 0-1 range when drawing rect', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({ mutate: createMock } as any)

      useAnnotationStore.getState().setIsDrawingRect(true)

      const { container } = renderOverlay(1)

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(overlay).toBeTruthy()

      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      fireEvent.mouseDown(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseMove(overlay, { clientX: 600, clientY: 700 })
      fireEvent.mouseUp(overlay)

      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          set_id: 'set-1',
          page_number: 1,
          type: 'rect',
          color: '#FF0000',
          rects: expect.arrayContaining([
            expect.objectContaining({ x: 0.5, y: 0.5, w: 0.25, h: expect.closeTo(0.2, 5) }),
          ]),
        })
      )
    })

    it('handles reverse drag (negative width/height)', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({ mutate: createMock } as any)

      useAnnotationStore.getState().setIsDrawingRect(true)

      const { container } = renderOverlay(1)

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      fireEvent.mouseDown(overlay, { clientX: 600, clientY: 700 })
      fireEvent.mouseMove(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseUp(overlay)

      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          set_id: 'set-1',
          page_number: 1,
          type: 'rect',
          color: '#FF0000',
          rects: expect.arrayContaining([
            expect.objectContaining({ x: 0.5, y: 0.5, w: 0.25, h: expect.closeTo(0.2, 5) }),
          ]),
        })
      )
    })

    it('ignores very small rectangles', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({ mutate: createMock } as any)

      useAnnotationStore.getState().setIsDrawingRect(true)

      const { container } = renderOverlay(1)

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      Object.defineProperty(overlay, 'getBoundingClientRect', {
        value: () => ({ left: 0, top: 0, width: 800, height: 1000, right: 800, bottom: 1000 }),
        writable: true,
      })

      fireEvent.mouseDown(overlay, { clientX: 400, clientY: 500 })
      fireEvent.mouseMove(overlay, { clientX: 405, clientY: 505 })
      fireEvent.mouseUp(overlay)

      expect(createMock).not.toHaveBeenCalled()
    })
  })

  describe('new interaction model', () => {
    it('overlay container is pointer-events-none by default', () => {
      useAnnotationStore.setState({ isDrawingRect: false, selectedSetId: 'set-1' })

      const { container } = renderOverlay(1)

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(overlay?.classList.contains('pointer-events-none')).toBe(true)
    })

    it('overlay container is pointer-events-auto when drawing rect', () => {
      useAnnotationStore.setState({ isDrawingRect: true, selectedSetId: 'set-1' })

      const { container } = renderOverlay(1)

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(overlay?.classList.contains('pointer-events-auto')).toBe(true)
      expect(overlay?.classList.contains('cursor-crosshair')).toBe(true)
    })

    it('annotation <g> elements have pointer-events all attribute', () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      useAnnotationStore.setState({ selectedSetId: 'set-1' })

      const { container } = renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      const g = container.querySelector('g')
      expect(g?.getAttribute('pointer-events')).toBe('all')
    })

    it('fires onContextMenu and sets store contextMenu on right-click annotation', () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      useAnnotationStore.setState({ selectedSetId: 'set-1' })

      const { container } = renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      const g = container.querySelector('g')!
      fireEvent.contextMenu(g, { clientX: 200, clientY: 300 })

      const { contextMenu, selectedAnnotationId } = useAnnotationStore.getState()
      expect(contextMenu).toEqual({ x: 200, y: 300, annotationId: 'ann-1' })
      expect(selectedAnnotationId).toBe('ann-1')
    })

    it('clears selection when clicking overlay background', () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')

      const { container } = renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      const overlay = container.querySelector('.absolute.inset-0') as HTMLElement
      fireEvent.click(overlay)

      expect(useAnnotationStore.getState().selectedAnnotationId).toBeNull()
    })

    it('does not draw when not in drawing mode', () => {
      const createMock = vi.fn()
      vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({ mutate: createMock } as any)

      useAnnotationStore.getState().setIsDrawingRect(false)

      const { container } = renderOverlay(1)

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
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'highlight', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FFFF00', selected_text: null, note_content: null, created_at: '', updated_at: '' },
        { id: 'ann-2', set_id: 'set-1', page_number: 2, type: 'highlight', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FFFF00', selected_text: null, note_content: null, created_at: '', updated_at: '' },
        { id: 'ann-3', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.5, y: 0.5, w: 0.1, h: 0.1 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      const { container } = renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      // Should render 2 annotations (page 1 only)
      const groups = container.querySelectorAll('g')
      expect(groups.length).toBe(2)
    })

    it('highlights selected annotation', () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')

      const { container } = renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      const svg = container.querySelector('svg')
      expect(svg).toBeTruthy()

      const groups = svg?.querySelectorAll('g')
      expect(groups?.length).toBe(1)

      const rect = svg?.querySelector('rect')
      expect(rect).toBeTruthy()
    })
  })

  describe('toolbar rendering', () => {
    it('renders toolbar when annotation is selected', () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      useAnnotationStore.getState().setSelectedAnnotationId('ann-1')

      const { container } = renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      const svg = container.querySelector('svg')
      expect(svg).toBeTruthy()
      const handles = svg?.querySelectorAll('rect[stroke="#3b82f6"]')
      expect(handles?.length).toBeGreaterThan(0)
    })

    it('does not render toolbar for annotation on different page (cross-page guard)', () => {
      const mockAnnotations: Annotation[] = [
        { id: 'ann-1', set_id: 'set-1', page_number: 1, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
        { id: 'ann-2', set_id: 'set-1', page_number: 2, type: 'rect', rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.05 }], color: '#FF0000', selected_text: null, note_content: null, created_at: '', updated_at: '' },
      ]

      useAnnotationStore.getState().setSelectedAnnotationId('ann-2')

      renderOverlay(1, buildAnnotationsContext(mockAnnotations))

      expect(screen.queryByTitle(/delete/i)).not.toBeInTheDocument()
    })
  })

  describe('null selected set', () => {
    it('returns null when no set is selected and no visible sets', () => {
      useAnnotationStore.getState().setSelectedSetId(null)

      const { container } = renderOverlay(1, buildAnnotationsContext([], []))

      expect(container.firstChild).toBeNull()
    })
  })
})
