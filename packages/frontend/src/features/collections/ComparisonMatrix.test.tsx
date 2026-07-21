/**
 * Tests for the ComparisonMatrix component.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@/test/test-utils'
import { ComparisonMatrix } from './ComparisonMatrix'

vi.mock('@/api/summaries', () => ({
    useCollectionComparison: vi.fn(),
    useBulkSummarizeCollection: vi.fn(),
    useGeneratePdfSummary: vi.fn(),
    useUpdatePdfSummary: vi.fn(),
}))

const {
    useCollectionComparison,
    useBulkSummarizeCollection,
    useGeneratePdfSummary,
    useUpdatePdfSummary,
} = await import('@/api/summaries')

const mockUseCollectionComparison = vi.mocked(useCollectionComparison)
const mockUseBulkSummarize = vi.mocked(useBulkSummarizeCollection)
const mockUseGenerate = vi.mocked(useGeneratePdfSummary)
const mockUseUpdate = vi.mocked(useUpdatePdfSummary)

function completeRow(id: string, title: string, method: string | null) {
    return {
        pdf_id: id,
        title,
        year: 2020,
        summary: {
            pdf_id: id,
            status: 'complete' as const,
            progress_pct: 100,
            error_message: null,
            tldr: 'tldr',
            problem: 'a problem',
            method,
            dataset: 'ds',
            result: 'res',
            contribution: 'contrib',
            key_claims: [],
            edited_fields: method !== null ? ['method'] : [],
            model: null,
            generated_at: null,
            updated_at: null,
        },
    }
}

function missingRow(id: string, title: string) {
    return { pdf_id: id, title, year: null, summary: null }
}

describe('ComparisonMatrix', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockUseBulkSummarize.mockReturnValue({
            mutate: vi.fn(),
            isPending: false,
        } as unknown as ReturnType<typeof useBulkSummarizeCollection>)
        mockUseGenerate.mockReturnValue({
            mutate: vi.fn(),
            isPending: false,
        } as unknown as ReturnType<typeof useGeneratePdfSummary>)
        mockUseUpdate.mockReturnValue({
            mutate: vi.fn(),
            isPending: false,
        } as unknown as ReturnType<typeof useUpdatePdfSummary>)
    })

    it('renders empty state when there are no rows', () => {
        mockUseCollectionComparison.mockReturnValue({
            data: { rows: [], missing_count: 0 },
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionComparison>)

        render(<ComparisonMatrix collectionId="col-1" />)

        expect(
            screen.getByText('No papers in this collection yet.'),
        ).toBeInTheDocument()
    })

    it('renders rows and a Generate button for missing summaries', () => {
        mockUseCollectionComparison.mockReturnValue({
            data: {
                rows: [
                    completeRow('p1', 'Paper One', 'm1'),
                    missingRow('p2', 'Paper Two'),
                ],
                missing_count: 1,
            },
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionComparison>)

        render(<ComparisonMatrix collectionId="col-1" />)

        expect(screen.getByText('Paper One')).toBeInTheDocument()
        expect(screen.getByText('Paper Two')).toBeInTheDocument()
        expect(screen.getByText(/1 without summary/i)).toBeInTheDocument()
        // Per-row Generate button for the missing row (exact match, not the
        // header "Generate missing" button).
        expect(
            screen.getByRole('button', { name: 'Generate' }),
        ).toBeInTheDocument()
    })

    it('shows a textarea when a cell is clicked and saves via PATCH', async () => {
        const mutateMock = vi.fn()
        mockUseUpdate.mockReturnValue({
            mutate: mutateMock,
            isPending: false,
        } as unknown as ReturnType<typeof useUpdatePdfSummary>)
        mockUseCollectionComparison.mockReturnValue({
            data: { rows: [completeRow('p1', 'Paper One', null)], missing_count: 0 },
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionComparison>)

        render(<ComparisonMatrix collectionId="col-1" />)

        // Click the Method cell value (shows '—' since method is null).
        const methodCell = screen.getByText('—')
        fireEvent.click(methodCell)

        // Textarea appears.
        const textarea = await screen.findByRole('textbox')
        expect(textarea).toBeInTheDocument()
        fireEvent.change(textarea, { target: { value: 'new method' } })

        fireEvent.click(screen.getByText('Save'))

        await waitFor(() => {
            expect(mutateMock).toHaveBeenCalledTimes(1)
        })
        const call = mutateMock.mock.calls[0][0]
        expect(call.pdfId).toBe('p1')
        expect(call.method).toBe('new method')
    })
})
