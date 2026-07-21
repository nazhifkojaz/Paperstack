import { render, screen } from '@testing-library/react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { CollectionDetailPage } from './CollectionDetailPage';
import { useCollectionOverview, useCollections } from '@/api/collections';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/collections');
vi.mock('@/api/collectionInsights', () => ({
  useCollectionDuplicates: vi.fn(() => ({ data: { pairs: [] } })),
  useCollectionInsight: vi.fn(() => ({ data: null })),
  useGenerateInsight: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

describe('CollectionDetailPage', () => {
  const mockUseCollectionOverview = vi.mocked(useCollectionOverview);
  const mockUseCollections = vi.mocked(useCollections);

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCollections.mockReturnValue({ data: [] } as unknown as ReturnType<typeof useCollections>);
  });

  function renderWithRoute(collectionId: string) {
    window.history.pushState({}, '', `/library/collection/${collectionId}/overview`);
    return render(
      <BrowserRouter>
        <Routes>
          <Route
            path="/library/collection/:collectionId/overview"
            element={<CollectionDetailPage />}
          />
        </Routes>
      </BrowserRouter>,
    );
  }

  it('shows loading state', () => {
    mockUseCollectionOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCollectionOverview>);

    renderWithRoute('col1');

    expect(screen.getByText('Overview')).toBeInTheDocument();
  });

  it('shows tabs for Overview, Compare, Timeline, Graph, Insights', () => {
    mockUseCollectionOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCollectionOverview>);

    renderWithRoute('col1');

    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Compare' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Timeline' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Graph' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Insights' })).toBeInTheDocument();
  });

  it('shows error state', () => {
    mockUseCollectionOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useCollectionOverview>);

    renderWithRoute('col1');

    expect(screen.getByText(/Failed to load/i)).toBeInTheDocument();
  });

  it('displays collection name from collections list', () => {
    mockUseCollections.mockReturnValue({
      data: [
        { id: 'col1', name: 'My Collection', user_id: 'u1', parent_id: null, position: 0, created_at: '' },
      ],
    } as unknown as ReturnType<typeof useCollections>);
    mockUseCollectionOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCollectionOverview>);

    renderWithRoute('col1');

    expect(screen.getByText('My Collection')).toBeInTheDocument();
  });

  it('displays overview stats when data is available', () => {
    mockUseCollections.mockReturnValue({
      data: [
        { id: 'col1', name: 'My Collection', user_id: 'u1', parent_id: null, position: 0, created_at: '' },
      ],
    } as unknown as ReturnType<typeof useCollections>);
    mockUseCollectionOverview.mockReturnValue({
      data: {
        paper_count: 5,
        indexed_count: 3,
        year_distribution: { '2024': 3, '2023': 2 },
        top_authors: [{ name: 'John Doe', count: 4 }],
        recent_papers: [{ id: 'p1', title: 'Recent Paper', filename: 'r.pdf' }],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCollectionOverview>);

    renderWithRoute('col1');

    expect(screen.getByText('My Collection')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Papers')).toBeInTheDocument();
    expect(screen.getByText('Indexed')).toBeInTheDocument();
    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.getByText('Recent Paper')).toBeInTheDocument();
  });
});
