import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@/test/test-utils'
import { NotePopover } from './NotePopover'
import { createMockAnnotation } from '@/test/test-utils'
import * as annotationsApi from '@/api/annotations'

vi.mock('@/api/annotations', () => ({
    useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

describe('NotePopover', () => {
    const mockOnClose = vi.fn()
    const mockContainerDims = { width: 800, height: 1000 }

    const selectTab = (name: RegExp) => {
        const tab = screen.getByRole('tab', { name })
        fireEvent.pointerDown(tab, { button: 0, ctrlKey: false, pointerType: 'mouse' })
        fireEvent.mouseDown(tab, { button: 0, ctrlKey: false })
        fireEvent.mouseUp(tab)
        fireEvent.click(tab)
    }

    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('renders existing note content in view mode', () => {
        const annotation = createMockAnnotation({
            type: 'note',
            note_content: 'existing note text',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        expect(screen.getByText('existing note text')).toBeInTheDocument()
        expect(screen.queryByPlaceholderText(/add a note/i)).not.toBeInTheDocument()
        expect(screen.getByRole('button', { name: /edit note/i })).toBeInTheDocument()
    })

    it('enters edit mode when clicking Edit Note on existing note', () => {
        const annotation = createMockAnnotation({
            type: 'note',
            note_content: 'existing note text',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        fireEvent.click(screen.getByRole('button', { name: /edit note/i }))

        const textarea = screen.getByPlaceholderText(/add a note/i)
        expect(textarea).toHaveValue('existing note text')
    })

    it('renders empty textarea for new note', () => {
        const annotation = createMockAnnotation({
            type: 'note',
            note_content: null,
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        const textarea = screen.getByPlaceholderText(/add a note/i)
        expect(textarea).toHaveValue('')
    })

    it('calls useUpdateAnnotation on save', () => {
        const mutateMock = vi.fn()
        vi.mocked(annotationsApi.useUpdateAnnotation).mockReturnValue({
            mutate: mutateMock,
        } as any)

        const annotation = createMockAnnotation({
            id: 'note-1',
            type: 'note',
            note_content: null,
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        const textarea = screen.getByPlaceholderText(/add a note/i)
        fireEvent.change(textarea, { target: { value: 'new note content' } })

        const saveButton = screen.getByRole('button', { name: /save/i })
        fireEvent.click(saveButton)

        expect(mutateMock).toHaveBeenCalledWith({
            id: 'note-1',
            data: { note_content: 'new note content' },
        })
        expect(mockOnClose).toHaveBeenCalled()
    })

    it('closes on Escape key', () => {
        const annotation = createMockAnnotation({ type: 'note' })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        fireEvent.keyDown(screen.getByPlaceholderText(/add a note/i), { key: 'Escape' })
        expect(mockOnClose).toHaveBeenCalled()
    })

    it('closes when clicking outside', () => {
        const annotation = createMockAnnotation({ type: 'note' })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        // Click outside the popover
        fireEvent.mouseDown(document.body)

        expect(mockOnClose).toHaveBeenCalled()
    })

    it('does not close when clicking inside a Radix portal (e.g. Select dropdown)', () => {
        const annotation = createMockAnnotation({ type: 'note' })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        // Simulate a Radix Select portal rendered to document.body
        const portal = document.createElement('div')
        portal.setAttribute('data-radix-popper-content-wrapper', '')
        const option = document.createElement('div')
        option.textContent = 'Simpler'
        portal.appendChild(option)
        document.body.appendChild(portal)

        fireEvent.mouseDown(option)

        expect(mockOnClose).not.toHaveBeenCalled()

        document.body.removeChild(portal)
    })

    it('renders AI badge and strips header for AI-generated explanations', () => {
        const annotation = createMockAnnotation({
            type: 'highlight',
            note_content: '[AI Explanation — 2026-04-25 13:20 UTC] This passage explains that **attention mechanisms** are a core part.',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        expect(screen.getByText('AI Explanation')).toBeInTheDocument()
        expect(screen.getByText('2026-04-25 13:20 UTC')).toBeInTheDocument()
        expect(screen.getByText(/attention mechanisms/i)).toBeInTheDocument()
        expect(screen.queryByText(/\[AI Explanation/)).not.toBeInTheDocument()
    })

    it('does not render AI badge for regular user notes', () => {
        const annotation = createMockAnnotation({
            type: 'note',
            note_content: 'This is a regular user note without AI header.',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        expect(screen.queryByText('AI Explanation')).not.toBeInTheDocument()
        expect(screen.getByText(/regular user note/i)).toBeInTheDocument()
    })

    it('renders metadata-backed AI explanations on the explanation tab', () => {
        const annotation = createMockAnnotation({
            type: 'highlight',
            note_content: null,
            metadata: {
                ai_explanation: {
                    content: 'Generated explanation body.',
                    generated_at: '2026-04-25 13:20 UTC',
                },
            },
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        expect(screen.getByText('AI Explanation')).toBeInTheDocument()
        expect(screen.getByText('Generated explanation body.')).toBeInTheDocument()
    })

    it('renders metadata-backed AI paraphrases on the paraphrase tab', () => {
        const annotation = createMockAnnotation({
            type: 'highlight',
            note_content: null,
            metadata: {
                ai_paraphrase: {
                    content: 'Generated paraphrase body.',
                    generated_at: '2026-04-25 13:20 UTC',
                    level: 'simpler',
                },
            },
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        expect(screen.getByText('AI Paraphrase')).toBeInTheDocument()
        expect(screen.getByText('Simpler')).toBeInTheDocument()
        expect(screen.getByText('Generated paraphrase body.')).toBeInTheDocument()
    })

    it('shows a copy button on the paraphrase tab and copies content to clipboard', async () => {
        const annotation = createMockAnnotation({
            type: 'highlight',
            note_content: null,
            metadata: {
                ai_paraphrase: {
                    content: 'Generated paraphrase body.',
                    generated_at: '2026-04-25 13:20 UTC',
                    level: 'simpler',
                },
            },
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
            />
        )

        const copyButton = screen.getByTitle('Copy to clipboard')
        fireEvent.click(copyButton)

        expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Generated paraphrase body.')
        await waitFor(() => {
            expect(screen.getByText('Copied!')).toBeInTheDocument()
        })
    })

    it('renders the explain action on the explanation tab', () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: 'selected text',
            note_content: 'existing note',
        })
        const onExplainThis = vi.fn()

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                onExplainThis={onExplainThis}
            />
        )

        selectTab(/explanation/i)

        const explainButton = screen.getByRole('button', { name: /explain this/i })
        expect(explainButton).toBeInTheDocument()

        fireEvent.click(explainButton)
        expect(onExplainThis).toHaveBeenCalledWith('ann-1')
    })

    it('renders Ask in Chat and calls handler when clicked', () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: 'selected text',
            note_content: 'existing note',
        })
        const onAskInChat = vi.fn()

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                onAskInChat={onAskInChat}
            />
        )

        const askButton = screen.getByRole('button', { name: /ask in chat/i })
        expect(askButton).toBeInTheDocument()

        fireEvent.click(askButton)
        expect(onAskInChat).toHaveBeenCalledWith('ann-1')
    })

    it('disables Ask in Chat when highlight has no selected text', () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: '',
            note_content: 'existing note',
        })
        const onAskInChat = vi.fn()

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                onAskInChat={onAskInChat}
            />
        )

        const askButton = screen.getByRole('button', { name: /ask in chat/i })
        expect(askButton).toBeDisabled()

        fireEvent.click(askButton)
        expect(onAskInChat).not.toHaveBeenCalled()
    })

    it('only shows Edit Note on the note tab', () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: 'selected text',
            note_content: 'existing note',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                onExplainThis={vi.fn()}
                onParaphraseThis={vi.fn()}
            />
        )

        expect(screen.getByRole('button', { name: /edit note/i })).toBeInTheDocument()

        selectTab(/explanation/i)
        expect(screen.queryByRole('button', { name: /edit note/i })).not.toBeInTheDocument()

        selectTab(/paraphrase/i)
        expect(screen.queryByRole('button', { name: /edit note/i })).not.toBeInTheDocument()
    })

    it('renders the paraphrase controls on the paraphrase tab', () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: 'selected text',
            note_content: 'existing note',
        })
        const onParaphraseThis = vi.fn()

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                onParaphraseThis={onParaphraseThis}
            />
        )

        selectTab(/paraphrase/i)

        expect(screen.getAllByText('Same level').length).toBeGreaterThan(0)
        const paraphraseButton = screen.getByRole('button', { name: /paraphrase this/i })
        expect(paraphraseButton).toBeInTheDocument()

        fireEvent.click(paraphraseButton)
        expect(onParaphraseThis).toHaveBeenCalledWith('ann-1', 'same')
    })

    it('selects the explanation tab while explanation generation is running', async () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: 'selected text',
            note_content: 'existing note',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                isExplaining
                explainStatusMessage="Generating explanation..."
                onExplainThis={vi.fn()}
            />
        )

        await waitFor(() => {
            expect(screen.getByRole('tab', { name: /explanation/i })).toHaveAttribute('data-state', 'active')
        })
    })

    it('selects the paraphrase tab while paraphrase generation is running', async () => {
        const annotation = createMockAnnotation({
            id: 'ann-1',
            type: 'highlight',
            selected_text: 'selected text',
            note_content: 'existing note',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerDims={mockContainerDims}
                onClose={mockOnClose}
                isParaphrasing
                paraphraseStatusMessage="Generating paraphrase..."
                onParaphraseThis={vi.fn()}
            />
        )

        await waitFor(() => {
            expect(screen.getByRole('tab', { name: /paraphrase/i })).toHaveAttribute('data-state', 'active')
        })
    })

    it('uses responsive width when container is narrower than preferred card width', () => {
        const annotation = createMockAnnotation({
            type: 'note',
            note_content: 'short note',
        })

        const narrowContainer = { width: 300, height: 400 }

        render(
            <NotePopover
                annotation={annotation}
                containerDims={narrowContainer}
                onClose={mockOnClose}
            />
        )

        const card = screen.getByTestId('note-popover-card')
        expect(card).toHaveStyle({ width: '284px' }) // 300 - 8*2
    })
})
