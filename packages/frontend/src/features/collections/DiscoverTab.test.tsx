import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@/test/test-utils'
import { DiscoverTab } from './DiscoverTab'

vi.mock('@/api/collectionRecommendations', () => ({
    useCollectionRecommendations: vi.fn(),
}))

const { useCollectionRecommendations } = await import(
    '@/api/collectionRecommendations'
)

const mockUseRecs = vi.mocked(useCollectionRecommendations)

function mockReturn(
    overrides: Partial<ReturnType<typeof useCollectionRecommendations>> = {},
): ReturnType<typeof useCollectionRecommendations> {
    return {
        data: undefined,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
        ...overrides,
    } as unknown as ReturnType<typeof useCollectionRecommendations>
}

describe('DiscoverTab', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockUseRecs.mockReturnValue(mockReturn())
    })

    it('renders CTA state and does not fire fetch on mount', () => {
        render(<DiscoverTab collectionId="col-1" />)

        expect(
            screen.getByText('Find papers you might be missing'),
        ).toBeInTheDocument()
        expect(screen.getByText('Find suggested papers')).toBeInTheDocument()
        // enabled=false on first render -> no fetch.
        expect(mockUseRecs).toHaveBeenCalledWith('col-1', false)
    })

    it('shows loading state then renders suggestion cards after click', async () => {
        // Before arming: CTA state (no data). After arming: isLoading=true,
        // then results. We simulate the armed+results render.
        mockUseRecs.mockImplementation((_id, enabled) => {
            if (!enabled) return mockReturn()
            return mockReturn({
                data: {
                    suggestions: [
                        {
                            openalex_id: 'W1',
                            title: 'Attention Is All You Need',
                            authors: [
                                'Vaswani',
                                'Shazeer',
                                'Parmar',
                                'Extra',
                                'Fifth',
                                'Sixth',
                            ],
                            year: 2017,
                            doi: '10.1234/abc',
                            cited_by_count: 8,
                        },
                    ],
                    papers_total: 12,
                    papers_with_refs: 9,
                    papers_without_doi: 0,
                },
            })
        })

        render(<DiscoverTab collectionId="col-1" />)

        fireEvent.click(screen.getByText('Find suggested papers'))

        await waitFor(() => {
            expect(
                screen.getByText('Attention Is All You Need'),
            ).toBeInTheDocument()
        })
        // "8 of 12 cite" badge.
        expect(screen.getByText('8 of 12 cite')).toBeInTheDocument()
        // Authors line: first 3 + "+3", with year.
        expect(
            screen.getByText(/Vaswani, Shazeer, Parmar \+3 · 2017/),
        ).toBeInTheDocument()
    })

    it('renders no-results state when suggestions is empty', async () => {
        mockUseRecs.mockImplementation((_id, enabled) => {
            if (!enabled) return mockReturn()
            return mockReturn({
                data: {
                    suggestions: [],
                    papers_total: 5,
                    papers_with_refs: 5,
                    papers_without_doi: 0,
                },
            })
        })

        render(<DiscoverTab collectionId="col-1" />)

        fireEvent.click(screen.getByText('Find suggested papers'))

        await waitFor(() => {
            expect(screen.getByText('No strong suggestions yet.')).toBeInTheDocument()
        })
        expect(screen.getByText('Suggested papers (0)')).toBeInTheDocument()
    })

    it('renders skipped-papers note when papers_without_doi > 0', async () => {
        mockUseRecs.mockImplementation((_id, enabled) => {
            if (!enabled) return mockReturn()
            return mockReturn({
                data: {
                    suggestions: [
                        {
                            openalex_id: 'W1',
                            title: 'A Paper',
                            authors: ['Author X'],
                            year: 2020,
                            doi: null,
                            cited_by_count: 3,
                        },
                    ],
                    papers_total: 10,
                    papers_with_refs: 7,
                    papers_without_doi: 3,
                },
            })
        })

        render(<DiscoverTab collectionId="col-1" />)

        fireEvent.click(screen.getByText('Find suggested papers'))

        await waitFor(() => {
            expect(
                screen.getByText(/have no DOI and can't contribute/),
            ).toBeInTheDocument()
        })
        // The "3 of 10 cite" badge.
        expect(screen.getByText('3 of 10 cite')).toBeInTheDocument()
    })

    it('renders nothing-to-scan message when papers_with_refs is 0', async () => {
        mockUseRecs.mockImplementation((_id, enabled) => {
            if (!enabled) return mockReturn()
            return mockReturn({
                data: {
                    suggestions: [],
                    papers_total: 3,
                    papers_with_refs: 0,
                    papers_without_doi: 3,
                },
            })
        })

        render(<DiscoverTab collectionId="col-1" />)

        fireEvent.click(screen.getByText('Find suggested papers'))

        await waitFor(() => {
            expect(
                screen.getByText(/None of the papers in this collection/),
            ).toBeInTheDocument()
        })
    })

    it('renders error state with retry button', async () => {
        mockUseRecs.mockImplementation((_id, enabled) => {
            if (!enabled) return mockReturn()
            return mockReturn({ isError: true })
        })

        render(<DiscoverTab collectionId="col-1" />)

        fireEvent.click(screen.getByText('Find suggested papers'))

        await waitFor(() => {
            expect(
                screen.getByText(/Couldn't fetch suggestions/),
            ).toBeInTheDocument()
        })
        expect(screen.getByText('Try again')).toBeInTheDocument()
    })
})
