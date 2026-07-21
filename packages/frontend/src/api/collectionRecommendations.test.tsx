import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useCollectionRecommendations } from './collectionRecommendations'

vi.mock('./client', () => {
    return { apiFetch: vi.fn() }
})

const { apiFetch } = await import('./client')

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: 0 },
            mutations: { retry: false },
        },
    })
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
}

describe('collectionRecommendations API hooks', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('does not fetch when enabled is false', async () => {
        const { result } = renderHook(
            () => useCollectionRecommendations('col-1', false),
            { wrapper: createWrapper() },
        )

        expect(result.current.fetchStatus).toBe('idle')
        expect(apiFetch).not.toHaveBeenCalled()
    })

    it('does not fetch when collectionId is null', async () => {
        const { result } = renderHook(
            () => useCollectionRecommendations(null, true),
            { wrapper: createWrapper() },
        )

        expect(result.current.fetchStatus).toBe('idle')
        expect(apiFetch).not.toHaveBeenCalled()
    })

    it('fetches recommendations when enabled with a collectionId', async () => {
        vi.mocked(apiFetch).mockResolvedValueOnce({
            suggestions: [
                {
                    openalex_id: 'W1',
                    title: 'Paper One',
                    authors: ['Author A'],
                    year: 2020,
                    doi: '10.1/x',
                    cited_by_count: 2,
                },
            ],
            papers_total: 5,
            papers_with_refs: 4,
            papers_without_doi: 1,
        })

        const { result } = renderHook(
            () => useCollectionRecommendations('col-1', true),
            { wrapper: createWrapper() },
        )

        await waitFor(() => expect(result.current.isSuccess).toBe(true))
        expect(apiFetch).toHaveBeenCalledWith(
            '/collections/col-1/recommendations',
        )
        expect(result.current.data?.suggestions).toHaveLength(1)
        expect(result.current.data?.papers_total).toBe(5)
    })
})
