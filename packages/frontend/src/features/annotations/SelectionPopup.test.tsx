/**
 * Tests for SelectionPopup component.
 * SelectionPopup is a floating toolbar that appears above text selections with a "Highlight" button.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { SelectionPopup } from './SelectionPopup'
import { useAnnotationStore } from '@/stores/annotationStore'
import * as annotationsApi from '@/api/annotations'

vi.mock('@/api/annotations', () => ({
  useCreateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useAnnotationSets: vi.fn(() => ({ data: [] })),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useParams: () => ({ pdfId: 'pdf-1' }) }
})

describe('SelectionPopup', () => {
  const mockSelectionRect = { x: 100, y: 50, width: 200, height: 20 }
  const mockNormalizedRects = [{ x: 0.1, y: 0.05, w: 0.2, h: 0.02 }]

  beforeEach(() => {
    vi.clearAllMocks()
    useAnnotationStore.setState({
      selectedSetId: 'set-1',
      isDrawingRect: false,
    })

    vi.mocked(annotationsApi.useAnnotationSets).mockReturnValue({
      data: [{ id: 'set-1', pdf_id: 'pdf-1', name: 'Default', color: '#FFFF00' }],
    } as any)
  })

  it('renders Highlight button only (no standalone Note button)', () => {
    render(
      <SelectionPopup
        selectionRect={mockSelectionRect}
        normalizedRects={mockNormalizedRects}
        selectedText="test text"
        pageNumber={1}
        onDismiss={vi.fn()}
      />
    )

    expect(screen.getByText('Highlight')).toBeInTheDocument()
    expect(screen.queryByText('Note')).not.toBeInTheDocument()
  })

  it('calls createAnnotation with set color on Highlight click', () => {
    const createMock = vi.fn()
    vi.mocked(annotationsApi.useCreateAnnotation).mockReturnValue({
      mutate: createMock,
    } as any)

    const onDismiss = vi.fn()

    render(
      <SelectionPopup
        selectionRect={mockSelectionRect}
        normalizedRects={mockNormalizedRects}
        selectedText="test text"
        pageNumber={1}
        onDismiss={onDismiss}
      />
    )

    fireEvent.click(screen.getByText('Highlight'))

    expect(createMock).toHaveBeenCalledWith(
      {
        set_id: 'set-1',
        page_number: 1,
        type: 'highlight',
        rects: mockNormalizedRects,
        selected_text: 'test text',
        color: '#FFFF00',
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
      }),
    )

    // Simulate mutation success - onDismiss should be called via onSuccess callback
    const onSuccessArg = createMock.mock.calls[0][1]
    onSuccessArg?.onSuccess?.()
    expect(onDismiss).toHaveBeenCalled()
  })

  it('shows disabled state when no set is selected', () => {
    useAnnotationStore.setState({ selectedSetId: null })

    render(
      <SelectionPopup
        selectionRect={mockSelectionRect}
        normalizedRects={mockNormalizedRects}
        selectedText="test text"
        pageNumber={1}
        onDismiss={vi.fn()}
      />
    )

    expect(screen.getByText(/create.*set/i)).toBeInTheDocument()
  })
})
