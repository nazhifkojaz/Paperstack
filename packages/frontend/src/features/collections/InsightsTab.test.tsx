import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@/test/test-utils'
import { InsightsTab } from './InsightsTab'

vi.mock('@/api/collectionInsights', () => ({
    useCollectionInsight: vi.fn(),
    useGenerateInsight: vi.fn(),
}))

const { useCollectionInsight, useGenerateInsight } = await import(
    '@/api/collectionInsights'
)

const mockUseInsight = vi.mocked(useCollectionInsight)
const mockUseGenerate = vi.mocked(useGenerateInsight)

describe('InsightsTab', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockUseGenerate.mockReturnValue({
            mutate: vi.fn(),
            isPending: false,
            isError: false,
            error: null,
        } as unknown as ReturnType<typeof useGenerateInsight>)
    })

    it('shows empty state with Generate buttons when no insight', () => {
        mockUseInsight.mockReturnValue({
            data: null,
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionInsight>)

        render(<InsightsTab collectionId="col-1" />)

        expect(screen.getByText('Generate synthesis')).toBeInTheDocument()
        expect(
            screen.getByText('Find gaps & contradictions'),
        ).toBeInTheDocument()
    })

    it('renders generating state with skeleton', () => {
        mockUseInsight.mockImplementation((_id, kind) => ({
            data: {
                collection_id: 'col-1',
                kind,
                status: 'generating',
                progress_pct: 30,
                is_stale: false,
                payload: { paper_count: 5 },
                error_message: null,
                model: null,
                generated_at: null,
            },
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionInsight>))

        render(<InsightsTab collectionId="col-1" />, { router: true })

        // Both sections show "Analyzing" while generating.
        expect(screen.getAllByText(/Analyzing/i).length).toBeGreaterThan(0)
    })

    it('renders failed state with error message and Retry', () => {
        mockUseInsight.mockImplementation((_id, kind) => ({
            data: {
                collection_id: 'col-1',
                kind,
                status: 'failed',
                progress_pct: 100,
                is_stale: false,
                payload: null,
                error_message: 'Something broke',
                model: null,
                generated_at: null,
            },
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionInsight>))

        render(<InsightsTab collectionId="col-1" />, { router: true })

        // Both sections show the error.
        expect(screen.getAllByText('Something broke').length).toBeGreaterThan(0)
        expect(screen.getAllByText('Retry').length).toBeGreaterThan(0)
    })

    it('renders complete synthesis with narrative and themes', () => {
        mockUseInsight.mockImplementation((_id, kind) => {
            if (kind === 'synthesis') {
                return {
                    data: {
                        collection_id: 'col-1',
                        kind,
                        status: 'complete',
                        progress_pct: 100,
                        is_stale: false,
                        payload: {
                            synthesis: 'These papers relate.',
                            themes: [
                                {
                                    name: 'Theme A',
                                    description: 'desc',
                                    papers: [
                                        { pdf_id: 'p1', title: 'Paper One' },
                                    ],
                                },
                            ],
                        },
                        error_message: null,
                        model: 'test-model',
                        generated_at: '2026-07-10T10:00:00Z',
                    },
                    isLoading: false,
                } as unknown as ReturnType<typeof useCollectionInsight>
            }
            return {
                data: null,
                isLoading: false,
            } as unknown as ReturnType<typeof useCollectionInsight>
        })

        render(<InsightsTab collectionId="col-1" />, { router: true })

        expect(screen.getByText('These papers relate.')).toBeInTheDocument()
        expect(screen.getByText('Theme A')).toBeInTheDocument()
        expect(screen.getByText('Paper One')).toBeInTheDocument()
    })

    it('renders stale badge when is_stale is true', () => {
        mockUseInsight.mockImplementation((_id, kind) => {
            if (kind === 'synthesis') {
                return {
                    data: {
                        collection_id: 'col-1',
                        kind,
                        status: 'complete',
                        progress_pct: 100,
                        is_stale: true,
                        payload: { synthesis: 'Stale narrative' },
                        error_message: null,
                        model: null,
                        generated_at: '2026-07-10T10:00:00Z',
                    },
                    isLoading: false,
                } as unknown as ReturnType<typeof useCollectionInsight>
            }
            return {
                data: null,
                isLoading: false,
            } as unknown as ReturnType<typeof useCollectionInsight>
        })

        render(<InsightsTab collectionId="col-1" />, { router: true })

        expect(screen.getByText(/Outdated/i)).toBeInTheDocument()
    })

    it('calls generate mutate on button click', async () => {
        const mutateMock = vi.fn()
        mockUseGenerate.mockReturnValue({
            mutate: mutateMock,
            isPending: false,
            isError: false,
            error: null,
        } as unknown as ReturnType<typeof useGenerateInsight>)
        mockUseInsight.mockReturnValue({
            data: null,
            isLoading: false,
        } as unknown as ReturnType<typeof useCollectionInsight>)

        render(<InsightsTab collectionId="col-1" />, { router: true })

        fireEvent.click(screen.getByText('Generate synthesis'))

        await waitFor(() => {
            expect(mutateMock).toHaveBeenCalledWith('col-1')
        })
    })
})
