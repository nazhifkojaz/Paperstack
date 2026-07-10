import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useUpdateCollection, useDeleteCollection, useExportCollection } from './collections'

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
