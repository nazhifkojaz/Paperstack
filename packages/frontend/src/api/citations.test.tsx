import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useValidateCitations, useBulkExportCitations, useLookupCitation } from './citations'

// Mock the API client
vi.mock('./client', () => ({
  apiFetch: vi.fn(),
  apiFetchBlob: vi.fn(),
}))

const { apiFetch, apiFetchBlob } = await import('./client')

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('citations API hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useValidateCitations', () => {
    it('should call validate endpoint with PDF IDs', async () => {
      const mockResponse = {
        has_citation: ['pdf1', 'pdf2'],
        missing: ['pdf3'],
      }
      vi.mocked(apiFetch).mockResolvedValueOnce(mockResponse)

      const { result } = renderHook(() => useValidateCitations(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync(['pdf1', 'pdf2', 'pdf3'])

      expect(apiFetch).toHaveBeenCalledWith('/citations/validate', {
        method: 'POST',
        // Content-Type header is auto-added by apiFetch for non-FormData bodies
        body: JSON.stringify({ pdf_ids: ['pdf1', 'pdf2', 'pdf3'] }),
      })
    })
  })

  describe('useBulkExportCitations', () => {
    it('should call export endpoint and return blob', async () => {
      const mockBlob = new Blob(['@article{test}'], { type: 'text/plain' })
      vi.mocked(apiFetchBlob).mockResolvedValueOnce(mockBlob)

      // Mock browser APIs for download
      const mockUrl = 'blob:mock-url'
      const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue(mockUrl)
      const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

      // Spy on createElement to track anchor creation but not interfere with React
      const createElementSpy = vi.spyOn(document, 'createElement')

      const { result } = renderHook(() => useBulkExportCitations(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({
        pdf_ids: ['pdf1', 'pdf2'],
        format: 'bibtex',
      })

      expect(apiFetchBlob).toHaveBeenCalledWith('/citations/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_ids: ['pdf1', 'pdf2'],
          format: 'bibtex',
        }),
      })

      // Verify anchor element was created with 'a' tag
      expect(createElementSpy).toHaveBeenCalledWith('a')
      // Verify blob URL was created
      expect(createObjectURLSpy).toHaveBeenCalledWith(mockBlob)
      // Verify blob URL was revoked
      expect(revokeObjectURLSpy).toHaveBeenCalledWith(mockUrl)

      createObjectURLSpy.mockRestore()
      revokeObjectURLSpy.mockRestore()
      createElementSpy.mockRestore()
    })
  })

  describe('useLookupCitation', () => {
    it('should call lookup endpoint with DOI', async () => {
      const mockResponse = {
        doi: '10.1234/test.doi',
        isbn: null,
        title: 'Test Paper Title',
        authors: 'John Doe',
        year: 2024,
        bibtex: '@article{test2024}',
        csl_json: null,
        source: 'crossref' as const,
      }
      vi.mocked(apiFetch).mockResolvedValueOnce(mockResponse)

      const { result } = renderHook(() => useLookupCitation(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({ doi: '10.1234/test.doi' })

      expect(apiFetch).toHaveBeenCalledWith('/citations/lookup', {
        method: 'POST',
        body: JSON.stringify({ doi: '10.1234/test.doi' }),
      })
    })

    it('should call lookup endpoint with ISBN', async () => {
      const mockResponse = {
        doi: null,
        isbn: '0262033844',
        title: 'Introduction to Algorithms',
        authors: 'Thomas H. Cormen',
        year: 2009,
        bibtex: '@book{cormen2009}',
        csl_json: null,
        source: 'openlibrary' as const,
      }
      vi.mocked(apiFetch).mockResolvedValueOnce(mockResponse)

      const { result } = renderHook(() => useLookupCitation(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({ isbn: '0262033844' })

      expect(apiFetch).toHaveBeenCalledWith('/citations/lookup', {
        method: 'POST',
        body: JSON.stringify({ isbn: '0262033844' }),
      })
    })

    it('should propagate error on failure', async () => {
      vi.mocked(apiFetch).mockRejectedValueOnce(new Error('DOI not found'))

      const { result } = renderHook(() => useLookupCitation(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({ doi: '10.9999/nonexistent' })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
      expect(result.current.error?.message).toBe('DOI not found')
    })
  })
})
