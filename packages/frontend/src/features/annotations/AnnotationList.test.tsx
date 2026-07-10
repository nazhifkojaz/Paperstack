import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { SetAnnotationList } from './AnnotationList'
import { useAnnotationStore } from '@/stores/annotationStore'
import { useNewPdfViewerStore } from '@/features/pdf-viewer/pdfViewerStore'
import * as annotationsApi from '@/api/annotations'
import { requestAnnotationRelocation } from '@/features/pdf-viewer/useTextIndexMatcher'
import { createMockAnnotation } from '@/test/test-utils'

vi.mock('@/api/annotations', () => ({
  useAnnotations: vi.fn(() => ({ data: [], isLoading: false })),
  useDeleteAnnotation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

vi.mock('@/api/colorLabels', () => ({
  useColorLabels: vi.fn(() => ({
    data: {
      '#22c55e': 'Findings',
      '#3b82f6': 'Methods',
      '#a855f7': 'Definitions',
      '#f97316': 'Limitations',
      '#6b7280': 'Background',
      '#FFFF00': 'Highlights',
      '#EF4444': 'Important',
      '#00FFFF': 'Follow-up',
    },
  })),
  useUpdateColorLabels: vi.fn(() => ({ mutate: vi.fn() })),
}))

vi.mock('@/api/chat', () => ({
  useExplainAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useParaphraseAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

vi.mock('@/features/pdf-viewer/useTextIndexMatcher', () => ({
  requestAnnotationRelocation: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('SetAnnotationList', () => {
  const mockAnnotations = [
    createMockAnnotation({ id: 'ann-1', page_number: 1, type: 'highlight', selected_text: 'Important finding about methods', color: '#FFFF00' }),
    createMockAnnotation({ id: 'ann-2', page_number: 1, type: 'rect', color: '#EF4444' }),
    createMockAnnotation({ id: 'ann-3', page_number: 3, type: 'highlight', selected_text: 'Another result', color: '#3b82f6' }),
  ]

  const selectTab = (name: RegExp) => {
    const tab = screen.getByRole('tab', { name })
    fireEvent.pointerDown(tab, { button: 0, ctrlKey: false, pointerType: 'mouse' })
    fireEvent.mouseDown(tab, { button: 0, ctrlKey: false })
    fireEvent.mouseUp(tab)
    fireEvent.click(tab)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useAnnotationStore.setState({
      selectedSetId: 'set-1',
      selectedAnnotationId: null,
      sidebarGroupBy: 'page',
    })
    useNewPdfViewerStore.getState().reset()
    vi.mocked(annotationsApi.useAnnotations).mockReturnValue({
      data: mockAnnotations,
      isLoading: false,
    } as any)
    vi.mocked(annotationsApi.useDeleteAnnotation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any)
    vi.mocked(annotationsApi.useUpdateAnnotation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any)
  })

  it('groups annotations by page', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    expect(screen.getByText(/Page 1/)).toBeInTheDocument()
    expect(screen.getByText(/Page 3/)).toBeInTheDocument()
  })

  it('shows per-color count breakdown in By Page mode', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    // Page 1: yellow highlight + red rect
    expect(screen.getByTitle('Highlights: 1')).toBeInTheDocument()
    expect(screen.getByTitle('Important: 1')).toBeInTheDocument()
    // Page 3: blue highlight
    expect(screen.getByTitle('Methods: 1')).toBeInTheDocument()
  })

  it('does not show color breakdown in By Color mode', () => {
    render(<SetAnnotationList setId="set-1" groupBy="color" />)
    expect(screen.queryByTitle('Highlights: 1')).not.toBeInTheDocument()
  })

  it('groups annotations by color when toggled', () => {
    render(<SetAnnotationList setId="set-1" groupBy="color" />)
    expect(screen.getByText(/Highlights/)).toBeInTheDocument()
    expect(screen.getByText(/Methods/)).toBeInTheDocument()
  })

  it('shows preview text for highlights', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    expect(screen.getByText(/Important finding/)).toBeInTheDocument()
  })

  it('shows "Rectangle" label for rect annotations', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    expect(screen.getByText('Rectangle')).toBeInTheDocument()
  })

  it('sets selectedAnnotationId on click', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    const item = screen.getByText(/Important finding/)
    fireEvent.click(item.closest('[data-annotation-id]')!)
    expect(useAnnotationStore.getState().selectedAnnotationId).toBe('ann-1')
  })

  it('uses explicit page jump on click', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    const item = screen.getByText(/Another result/)
    fireEvent.click(item.closest('[data-annotation-id]')!)
    expect(useNewPdfViewerStore.getState().targetPage).toBe(3)
  })

  it('shows empty state when no annotations', () => {
    vi.mocked(annotationsApi.useAnnotations).mockReturnValue({
      data: [],
      isLoading: false,
    } as any)
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    expect(screen.getByText(/no annotations/i)).toBeInTheDocument()
  })

  it('retries relocation for unlocated annotations', () => {
    vi.mocked(annotationsApi.useAnnotations).mockReturnValue({
      data: [
        createMockAnnotation({
          id: 'ann-unlocated',
          page_number: 2,
          selected_text: 'Missing quote',
          rects: [],
        }),
      ],
      isLoading: false,
    } as any)

    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    fireEvent.click(screen.getByRole('button', { name: /retry locating annotation/i }))

    expect(requestAnnotationRelocation).toHaveBeenCalledWith('ann-unlocated')
    expect(useAnnotationStore.getState().selectedAnnotationId).toBe('ann-unlocated')
    expect(useNewPdfViewerStore.getState().targetPage).toBe(2)
  })

  it('deletes an annotation after confirmation', () => {
    const mutate = vi.fn((_variables, options) => options?.onSuccess?.())
    vi.mocked(annotationsApi.useDeleteAnnotation).mockReturnValue({
      mutate,
      isPending: false,
    } as any)

    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    fireEvent.click(screen.getAllByRole('button', { name: /delete annotation/i })[0])
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(mutate).toHaveBeenCalledWith(
      { id: 'ann-1', setId: 'set-1' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it('opens the annotation detail drawer', () => {
    render(<SetAnnotationList setId="set-1" pdfId="pdf-1" groupBy="page" />)
    fireEvent.click(screen.getAllByRole('button', { name: /open annotation details/i })[0])

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Annotated text')).toBeInTheDocument()
    expect(screen.getAllByText(/Important finding/).length).toBeGreaterThan(0)

    selectTab(/paraphrase/i)
    expect(screen.getByRole('button', { name: /paraphrase this/i })).toBeEnabled()
  })

  it('shows disabled drawer AI actions for highlights without selected text', () => {
    vi.mocked(annotationsApi.useAnnotations).mockReturnValue({
      data: [
        createMockAnnotation({
          id: 'ann-empty-highlight',
          page_number: 1,
          type: 'highlight',
          selected_text: '',
        }),
      ],
      isLoading: false,
    } as any)

    render(<SetAnnotationList setId="set-1" pdfId="pdf-1" groupBy="page" />)
    fireEvent.click(screen.getByRole('button', { name: /open annotation details/i }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('No selected text for this annotation.')).toBeInTheDocument()

    selectTab(/explanation/i)
    expect(screen.getByRole('button', { name: /explain this/i })).toBeDisabled()

    selectTab(/paraphrase/i)
    expect(screen.getByRole('button', { name: /paraphrase this/i })).toBeDisabled()
  })
})
