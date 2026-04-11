import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { AnnotationContextMenu } from './AnnotationContextMenu'
import { useAnnotationStore } from '@/stores/annotationStore'
import * as annotationsApi from '@/api/annotations'
import { createMockAnnotation } from '@/test/test-utils'

vi.mock('@/api/annotations', () => ({
  useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
  useDeleteAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

describe('AnnotationContextMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAnnotationStore.setState({ contextMenu: null, selectedAnnotationId: null })
  })

  it('renders menu items for a highlight annotation', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
      />
    )

    expect(screen.getByText(/note/i)).toBeInTheDocument()
    expect(screen.getByText(/color/i)).toBeInTheDocument()
    expect(screen.getByText(/copy/i)).toBeInTheDocument()
    expect(screen.getByText(/delete/i)).toBeInTheDocument()
  })

  it('does not show Copy Text for rect annotations', () => {
    const annotation = createMockAnnotation({ type: 'rect' })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
      />
    )

    expect(screen.queryByText(/copy/i)).not.toBeInTheDocument()
  })

  it('shows explain uses remaining when explainUsesRemaining is a non-negative number', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
        explainUsesRemaining={3}
      />
    )

    expect(screen.getByText(/3 explain uses remaining/i)).toBeInTheDocument()
  })

  it('shows singular "1 explain use remaining" for value of 1', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
        explainUsesRemaining={1}
      />
    )

    expect(screen.getByText(/1 explain use remaining/i)).toBeInTheDocument()
  })

  it('hides quota hint when explainUsesRemaining is null (before first call)', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
        explainUsesRemaining={null}
      />
    )

    expect(screen.queryByText(/explain use/i)).not.toBeInTheDocument()
  })

  it('hides quota hint when explainUsesRemaining is -1 (own-key user)', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
        explainUsesRemaining={-1}
      />
    )

    expect(screen.queryByText(/explain use/i)).not.toBeInTheDocument()
  })

  it('hides quota hint when explainUsesRemaining prop is omitted', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
      />
    )

    expect(screen.queryByText(/explain use/i)).not.toBeInTheDocument()
  })

  it('hides quota hint for non-highlight annotations even with explainUsesRemaining', () => {
    const annotation = createMockAnnotation({ type: 'rect' })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
        explainUsesRemaining={5}
      />
    )

    expect(screen.queryByText(/explain use/i)).not.toBeInTheDocument()
  })

  it('calls deleteAnnotation and onClose on Delete click', () => {
    const deleteMock = vi.fn()
    vi.mocked(annotationsApi.useDeleteAnnotation).mockReturnValue({
      mutate: deleteMock,
    } as any)

    const annotation = createMockAnnotation({ id: 'ann-1', set_id: 'set-1' })
    const onClose = vi.fn()

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={onClose}
        onEditNote={vi.fn()}
      />
    )

    fireEvent.click(screen.getByText(/delete/i))

    expect(deleteMock).toHaveBeenCalledWith({ id: 'ann-1', setId: 'set-1' })
    expect(onClose).toHaveBeenCalled()
  })
})
