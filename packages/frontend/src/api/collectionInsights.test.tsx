import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useCollectionInsight, useGenerateInsight } from './collectionInsights'

vi.mock('./client', () => {
    class ApiError extends Error {
        status: number
        code: string
        constructor(status: number, code: string, message: string) {
            super(message)
            this.name = 'ApiError'
            this.status = status
            this.code = code
        }
    }
    return { apiFetch: vi.fn(), ApiError }
})

const { apiFetch, ApiError } = await import('./client')

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

describe('collectionInsights API hooks', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('useCollectionInsight resolves null on 404 ApiError', async () => {
        vi.mocked(apiFetch).mockRejectedValueOnce(
            new ApiError(404, 'not_found', 'No insight'),
        )

        const { result } = renderHook(
            () => useCollectionInsight('col-1', 'synthesis'),
            { wrapper: createWrapper() },
        )

        await waitFor(() => expect(result.current.isSuccess).toBe(true))
        expect(result.current.data).toBeNull()
    })

    it('useGenerateInsight POSTs the synthesis endpoint', async () => {
        vi.mocked(apiFetch).mockResolvedValueOnce({
            collection_id: 'col-1',
            kind: 'synthesis',
            status: 'generating',
            progress_pct: 0,
            is_stale: false,
            payload: null,
            error_message: null,
            model: null,
            generated_at: null,
        })

        const { result } = renderHook(() => useGenerateInsight('synthesis'), {
            wrapper: createWrapper(),
        })

        await result.current.mutateAsync('col-1')

        expect(apiFetch).toHaveBeenCalledWith('/collections/col-1/synthesize', {
            method: 'POST',
        })
    })

    it('useGenerateInsight POSTs the gaps endpoint', async () => {
        vi.mocked(apiFetch).mockResolvedValueOnce({
            collection_id: 'col-1',
            kind: 'gaps',
            status: 'generating',
            progress_pct: 0,
            is_stale: false,
            payload: null,
            error_message: null,
            model: null,
            generated_at: null,
        })

        const { result } = renderHook(() => useGenerateInsight('gaps'), {
            wrapper: createWrapper(),
        })

        await result.current.mutateAsync('col-1')

        expect(apiFetch).toHaveBeenCalledWith(
            '/collections/col-1/insights/gaps',
            { method: 'POST' },
        )
    })
})
