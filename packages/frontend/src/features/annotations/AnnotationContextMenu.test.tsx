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

  it('shows AI uses remaining when aiUsesRemaining is a non-negative number', () => {
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
        aiUsesRemaining={3}
      />
    )

    expect(screen.getByText(/3 ai uses remaining/i)).toBeInTheDocument()
  })

  it('shows singular "1 AI use remaining" for value of 1', () => {
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
        aiUsesRemaining={1}
      />
    )

    expect(screen.getByText(/1 ai use remaining/i)).toBeInTheDocument()
  })

  it('hides quota hint when aiUsesRemaining is null (before first call)', () => {
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
        aiUsesRemaining={null}
      />
    )

    expect(screen.queryByText(/ai use/i)).not.toBeInTheDocument()
  })

  it('hides quota hint when aiUsesRemaining is -1 (own-key user)', () => {
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
        aiUsesRemaining={-1}
      />
    )

    expect(screen.queryByText(/ai use/i)).not.toBeInTheDocument()
  })

  it('hides quota hint when aiUsesRemaining prop is omitted', () => {
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

    expect(screen.queryByText(/ai use/i)).not.toBeInTheDocument()
  })

  it('hides quota hint for non-highlight annotations even with aiUsesRemaining', () => {
    const annotation = createMockAnnotation({ type: 'rect' })

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={vi.fn()}
        aiUsesRemaining={5}
      />
    )

    expect(screen.queryByText(/ai use/i)).not.toBeInTheDocument()
  })

  it('calls onParaphraseThis and closes when Paraphrase This is clicked', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: 'test text',
    })
    const onParaphraseThis = vi.fn()
    const onClose = vi.fn()

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={onClose}
        onEditNote={vi.fn()}
        onParaphraseThis={onParaphraseThis}
      />
    )

    fireEvent.click(screen.getByText(/paraphrase this/i))

    expect(onParaphraseThis).toHaveBeenCalledWith(annotation.id)
    expect(onClose).toHaveBeenCalled()
  })

  it('shows disabled AI actions for highlight annotations without selected text', () => {
    const annotation = createMockAnnotation({
      type: 'highlight',
      selected_text: '',
    })
    const onExplainThis = vi.fn()
    const onParaphraseThis = vi.fn()

    render(
      <AnnotationContextMenu
        annotation={annotation}
        position={{ x: 100, y: 200 }}
        onClose={vi.fn()}
        onEditNote={vi.fn()}
        onExplainThis={onExplainThis}
        onParaphraseThis={onParaphraseThis}
      />
    )

    const explainButton = screen.getByRole('button', { name: /explain this/i })
    const paraphraseButton = screen.getByRole('button', { name: /paraphrase this/i })

    expect(explainButton).toBeDisabled()
    expect(paraphraseButton).toBeDisabled()

    fireEvent.click(paraphraseButton)

    expect(onExplainThis).not.toHaveBeenCalled()
    expect(onParaphraseThis).not.toHaveBeenCalled()
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
