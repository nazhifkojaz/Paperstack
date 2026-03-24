import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { AnnotationToolbar } from './AnnotationToolbar'
import { createMockAnnotation } from '@/test/test-utils'
import * as annotationsApi from '@/api/annotations'

vi.mock('@/api/annotations', () => ({
    useUpdateAnnotation: vi.fn(() => ({ mutate: vi.fn() })),
}))

describe('AnnotationToolbar', () => {
    let mockContainerRef: React.RefObject<HTMLDivElement>

    beforeEach(() => {
        vi.clearAllMocks()
        const div = document.createElement('div')
        Object.defineProperty(div, 'offsetWidth', { value: 800 })
        Object.defineProperty(div, 'offsetHeight', { value: 1000 })
        mockContainerRef = { current: div }
    })

    it('does not render a delete button', () => {
        const annotation = createMockAnnotation({ type: 'rect' })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={vi.fn()}
            />
        )

        expect(screen.queryByTitle(/delete/i)).not.toBeInTheDocument()
    })

    it('renders color swatches', () => {
        const annotation = createMockAnnotation({ type: 'rect', color: '#EF4444' })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={vi.fn()}
            />
        )

        // Should render 6 color swatch buttons
        const swatches = screen.getAllByRole('button').filter(
            btn => btn.getAttribute('data-color')
        )
        expect(swatches.length).toBe(6)
    })

    it('renders note button for highlight and rect annotations', () => {
        const annotation = createMockAnnotation({ type: 'highlight', note_content: null })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={vi.fn()}
            />
        )

        expect(screen.getByTitle('Add note')).toBeInTheDocument()
    })

    it('shows Edit note title when note_content exists', () => {
        const annotation = createMockAnnotation({ type: 'rect', note_content: 'existing note' })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={vi.fn()}
            />
        )

        expect(screen.getByTitle('Edit note')).toBeInTheDocument()
    })

    it('does not render note button for standalone note annotations', () => {
        const annotation = createMockAnnotation({ type: 'note' })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={vi.fn()}
            />
        )

        expect(screen.queryByTitle(/note/i)).not.toBeInTheDocument()
    })

    it('calls onEditNote when note button is clicked', () => {
        const onEditNote = vi.fn()
        const annotation = createMockAnnotation({ type: 'rect' })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={onEditNote}
            />
        )

        fireEvent.click(screen.getByTitle('Add note'))
        expect(onEditNote).toHaveBeenCalledOnce()
    })

    it('calls update mutation on color swatch click', () => {
        const updateMock = vi.fn()
        vi.mocked(annotationsApi.useUpdateAnnotation).mockReturnValue({
            mutate: updateMock,
        } as any)

        const annotation = createMockAnnotation({ id: 'ann-1', type: 'rect', color: '#EF4444' })

        render(
            <AnnotationToolbar
                annotation={annotation}
                containerRef={mockContainerRef as any}
                onEditNote={vi.fn()}
            />
        )

        // Click a different color swatch (blue)
        const blueSwatch = screen.getAllByRole('button').find(
            btn => btn.getAttribute('data-color') === '#3B82F6'
        )
        expect(blueSwatch).toBeTruthy()
        fireEvent.click(blueSwatch!)

        expect(updateMock).toHaveBeenCalledWith({
            id: 'ann-1',
            data: { color: '#3B82F6' },
        })
    })
})
