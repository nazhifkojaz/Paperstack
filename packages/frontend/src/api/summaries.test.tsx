import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
    usePdfSummary,
    useUpdatePdfSummary,
    useBulkSummarizeCollection,
} from './summaries'

// Mock the API client. ApiError is provided as a real class so the
// `instanceof ApiError` / `e.status` checks in summaries.ts work.
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

describe('summaries API hooks', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('usePdfSummary resolves null on 404 ApiError', async () => {
        vi.mocked(apiFetch).mockRejectedValueOnce(
            new ApiError(404, 'not_found', 'No summary'),
        )

        const { result } = renderHook(() => usePdfSummary('pdf-1'), {
            wrapper: createWrapper(),
        })

        await waitFor(() => expect(result.current.isSuccess).toBe(true))
        expect(result.current.data).toBeNull()
    })

    it('useUpdatePdfSummary sends a PATCH body', async () => {
        vi.mocked(apiFetch).mockResolvedValueOnce({
            pdf_id: 'pdf-1',
            status: 'not_generated',
        })

        const { result } = renderHook(() => useUpdatePdfSummary(), {
            wrapper: createWrapper(),
        })

        await result.current.mutateAsync({ pdfId: 'pdf-1', method: 'edited' })

        expect(apiFetch).toHaveBeenCalledWith('/pdfs/pdf-1/summary', {
            method: 'PATCH',
            body: JSON.stringify({ method: 'edited' }),
        })
    })

    it('useBulkSummarizeCollection POSTs the bulk endpoint', async () => {
        vi.mocked(apiFetch).mockResolvedValueOnce({
            queued: ['a'],
            skipped_complete: 0,
            skipped_quota: 0,
            total_papers: 1,
        })

        const { result } = renderHook(() => useBulkSummarizeCollection(), {
            wrapper: createWrapper(),
        })

        await result.current.mutateAsync('col-1')

        expect(apiFetch).toHaveBeenCalledWith('/collections/col-1/summaries', {
            method: 'POST',
        })
    })
})
