import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useAddPdfToCollection,
  useDeleteCollection,
  useExportCollection,
  useRemovePdfFromCollection,
  useSwapCollectionPositions,
  useUpdateCollection,
} from './collections'

vi.mock('./client', () => ({
  apiFetch: vi.fn(),
  apiFetchBlob: vi.fn(),
}))

const { apiFetch, apiFetchBlob } = await import('./client')

function createTestWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: {
        retry: false,
      },
    },
  })
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

const createWrapper = () => createTestWrapper().wrapper

describe('collections API hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useUpdateCollection', () => {
    it('should call PATCH with collection data', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce({ id: 'col1', name: 'Updated' })

      const { result } = renderHook(() => useUpdateCollection(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({ id: 'col1', name: 'Updated' })

      expect(apiFetch).toHaveBeenCalledWith('/collections/col1', {
        method: 'PATCH',
        body: JSON.stringify({ name: 'Updated' }),
      })
    })

    it('should call PATCH with parent_id', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce({ id: 'col1' })

      const { result } = renderHook(() => useUpdateCollection(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({ id: 'col1', parent_id: 'parent1' })

      expect(apiFetch).toHaveBeenCalledWith('/collections/col1', {
        method: 'PATCH',
        body: JSON.stringify({ parent_id: 'parent1' }),
      })
    })
  })

  describe('useDeleteCollection', () => {
    it('should call DELETE for a collection', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

      const { result } = renderHook(() => useDeleteCollection(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync('col1')

      expect(apiFetch).toHaveBeenCalledWith('/collections/col1', {
        method: 'DELETE',
      })
    })
  })

  describe('useSwapCollectionPositions', () => {
    it('uses one request and invalidates collections once', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce([])
      const { queryClient, wrapper } = createTestWrapper()
      const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
      const { result } = renderHook(() => useSwapCollectionPositions(), { wrapper })

      await result.current.mutateAsync({ firstId: 'col1', secondId: 'col2' })

      expect(apiFetch).toHaveBeenCalledTimes(1)
      expect(apiFetch).toHaveBeenCalledWith('/collections/swap-positions', {
        method: 'POST',
        body: JSON.stringify({ first_id: 'col1', second_id: 'col2' }),
      })
      expect(invalidate).toHaveBeenCalledTimes(1)
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['collections'] })
    })
  })

  describe.each([
    ['add', useAddPdfToCollection, '/collections/col1/pdfs?pdf_id=pdf1', 'POST'],
    ['remove', useRemovePdfFromCollection, '/collections/col1/pdfs/pdf1', 'DELETE'],
  ] as const)('use %s membership mutation', (_name, useHook, url, method) => {
    it('invalidates every collection membership dependent query', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce(undefined)
      const { queryClient, wrapper } = createTestWrapper()
      const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
      const { result } = renderHook(() => useHook(), { wrapper })

      await result.current.mutateAsync({ pdfId: 'pdf1', collectionId: 'col1' })

      expect(apiFetch).toHaveBeenCalledWith(url, { method })
      expect(invalidate.mock.calls.map(([options]) => options?.queryKey)).toEqual([
        ['pdfs'],
        ['collections'],
        ['collection-overview', 'col1'],
        ['collection-comparison', 'col1'],
        ['collection-summaries', 'col1'],
        ['collection-insight', 'col1'],
        ['collection-recommendations', 'col1'],
        ['collection-duplicates', 'col1'],
      ])
      expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ['collection-insight'] })
    })
  })

  describe('useExportCollection', () => {
    it('should export as BibTeX', async () => {
      const mockBlob = new Blob(['@article{test}'], { type: 'text/plain' })
      vi.mocked(apiFetchBlob).mockResolvedValueOnce(mockBlob)

      const { result } = renderHook(() => useExportCollection(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({ id: 'col1', format: 'bibtex' })

      expect(apiFetchBlob).toHaveBeenCalledWith('/collections/col1/export?format=bibtex')
    })

    it('should export as Markdown', async () => {
      const mockBlob = new Blob(['# Collection'], { type: 'text/markdown' })
      vi.mocked(apiFetchBlob).mockResolvedValueOnce(mockBlob)

      const { result } = renderHook(() => useExportCollection(), {
        wrapper: createWrapper(),
      })

      await result.current.mutateAsync({ id: 'col1', format: 'markdown' })

      expect(apiFetchBlob).toHaveBeenCalledWith('/collections/col1/export?format=markdown')
    })
  })
})
