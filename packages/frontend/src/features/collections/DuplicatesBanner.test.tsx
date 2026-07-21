import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@/test/test-utils'
import { DuplicatesBanner } from './DuplicatesBanner'

vi.mock('@/api/collectionInsights', () => ({
    useCollectionDuplicates: vi.fn(),
}))

vi.mock('@/api/collections', () => ({
    useRemovePdfFromCollection: vi.fn(),
}))

vi.mock('sonner', () => ({
    toast: { success: vi.fn(), error: vi.fn() },
}))

const { useCollectionDuplicates } = await import('@/api/collectionInsights')
const { useRemovePdfFromCollection } = await import('@/api/collections')

const mockUseDuplicates = vi.mocked(useCollectionDuplicates)
const mockUseRemove = vi.mocked(useRemovePdfFromCollection)

describe('DuplicatesBanner', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockUseRemove.mockReturnValue({
            mutate: vi.fn(),
            isPending: false,
        } as unknown as ReturnType<typeof useRemovePdfFromCollection>)
    })

    it('renders nothing when pairs is empty', () => {
        mockUseDuplicates.mockReturnValue({
            data: { pairs: [] },
        } as unknown as ReturnType<typeof useCollectionDuplicates>)

        const { container } = render(<DuplicatesBanner collectionId="col-1" />)

        expect(container.firstChild).toBeNull()
    })

    it('renders nothing while loading (no data)', () => {
        mockUseDuplicates.mockReturnValue({
            data: undefined,
        } as unknown as ReturnType<typeof useCollectionDuplicates>)

        const { container } = render(<DuplicatesBanner collectionId="col-1" />)

        expect(container.firstChild).toBeNull()
    })

    it('renders duplicate pairs when present', () => {
        mockUseDuplicates.mockReturnValue({
            data: {
                pairs: [
                    {
                        pdf_a: { id: 'a', title: 'Paper A' },
                        pdf_b: { id: 'b', title: 'Paper B' },
                        similarity: 0.98,
                    },
                ],
            },
        } as unknown as ReturnType<typeof useCollectionDuplicates>)

        render(<DuplicatesBanner collectionId="col-1" />, { router: true })

        expect(screen.getByText(/Possible duplicates/)).toBeInTheDocument()
        expect(screen.getByText('Paper A')).toBeInTheDocument()
        expect(screen.getByText('Paper B')).toBeInTheDocument()
        expect(screen.getByText('98% similar')).toBeInTheDocument()
    })
})
