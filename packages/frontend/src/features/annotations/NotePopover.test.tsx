import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { NotePopover } from './NotePopover'
import { createMockAnnotation } from '@/test/test-utils'
import * as annotationsApi from '@/api/annotations'

vi.mock('@/api/annotations', () => ({
    useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

describe('NotePopover', () => {
    const mockOnClose = vi.fn()
    let mockContainerRef: React.RefObject<HTMLDivElement>

    beforeEach(() => {
        vi.clearAllMocks()
        // Create a container div with known dimensions
        const div = document.createElement('div')
        Object.defineProperty(div, 'offsetWidth', { value: 800 })
        Object.defineProperty(div, 'offsetHeight', { value: 1000 })
        mockContainerRef = { current: div }
    })

    it('renders existing note content in view mode', () => {
        const annotation = createMockAnnotation({
            type: 'note',
            note_content: 'existing note text',
        })

        render(
            <NotePopover
                annotation={annotation}
                containerRef={mockContainerRef as any}
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
                containerRef={mockContainerRef as any}
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
                containerRef={mockContainerRef as any}
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
                containerRef={mockContainerRef as any}
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
                containerRef={mockContainerRef as any}
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
                containerRef={mockContainerRef as any}
                onClose={mockOnClose}
            />
        )

        // Click outside the popover
        fireEvent.mouseDown(document.body)

        expect(mockOnClose).toHaveBeenCalled()
    })
})
