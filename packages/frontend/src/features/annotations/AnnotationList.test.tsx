import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { SetAnnotationList } from './AnnotationList'
import { useAnnotationStore } from '@/stores/annotationStore'
import * as annotationsApi from '@/api/annotations'
import { createMockAnnotation } from '@/test/test-utils'

vi.mock('@/api/annotations', () => ({
  useAnnotations: vi.fn(() => ({ data: [], isLoading: false })),
}))

describe('SetAnnotationList', () => {
  const mockAnnotations = [
    createMockAnnotation({ id: 'ann-1', page_number: 1, type: 'highlight', selected_text: 'Important finding about methods', color: '#FFFF00' }),
    createMockAnnotation({ id: 'ann-2', page_number: 1, type: 'rect', color: '#EF4444' }),
    createMockAnnotation({ id: 'ann-3', page_number: 3, type: 'highlight', selected_text: 'Another result', color: '#3B82F6' }),
  ]

  beforeEach(() => {
    useAnnotationStore.setState({
      selectedSetId: 'set-1',
      selectedAnnotationId: null,
      sidebarGroupBy: 'page',
    })
    vi.mocked(annotationsApi.useAnnotations).mockReturnValue({
      data: mockAnnotations,
      isLoading: false,
    } as any)
  })

  it('groups annotations by page', () => {
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    expect(screen.getByText(/Page 1/)).toBeInTheDocument()
    expect(screen.getByText(/Page 3/)).toBeInTheDocument()
  })

  it('groups annotations by type when toggled', () => {
    render(<SetAnnotationList setId="set-1" groupBy="type" />)
    expect(screen.getByText(/Highlights/)).toBeInTheDocument()
    expect(screen.getByText(/Rectangles/)).toBeInTheDocument()
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

  it('shows empty state when no annotations', () => {
    vi.mocked(annotationsApi.useAnnotations).mockReturnValue({
      data: [],
      isLoading: false,
    } as any)
    render(<SetAnnotationList setId="set-1" groupBy="page" />)
    expect(screen.getByText(/no annotations/i)).toBeInTheDocument()
  })
})
