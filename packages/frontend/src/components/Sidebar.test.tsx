import { render, screen } from '@testing-library/react';
import { Sidebar } from './Sidebar';
import { useLibraryStore } from '@/stores/libraryStore';
import { useCollections, useCreateCollection } from '@/api/collections';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the stores and hooks
vi.mock('@/stores/libraryStore');
vi.mock('@/api/collections');

describe('Sidebar', () => {
  const mockLibraryStore = vi.mocked(useLibraryStore);
  const mockUseCollections = vi.mocked(useCollections);
  const mockUseCreateCollection = vi.mocked(useCreateCollection);

  beforeEach(() => {
    vi.clearAllMocks();

    mockLibraryStore.mockReturnValue({
      selectedProjectId: null,
      setSelectedProjectId: vi.fn(),
      resetFilters: vi.fn(),
    });

    mockUseCollections.mockReturnValue({ data: [] } as unknown as ReturnType<typeof useCollections>);
    mockUseCreateCollection.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as unknown as ReturnType<typeof useCreateCollection>);
  });

  it('renders the sidebar with All Documents button', () => {
    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByRole('button', { name: /All Documents/i })).toBeInTheDocument();
  });

  it('renders Projects section header', () => {
    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('Projects')).toBeInTheDocument();
  });

  it('renders projects when data is present', () => {
    const mockProjects = [
      { id: '1', name: 'Research Paper', user_id: 'u1', parent_id: null, position: 0, created_at: '' },
    ];
    mockUseCollections.mockReturnValue({ data: mockProjects } as unknown as ReturnType<typeof useCollections>);

    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('Research Paper')).toBeInTheDocument();
  });

  it('shows empty state when no projects exist', () => {
    mockUseCollections.mockReturnValue({ data: [] } as unknown as ReturnType<typeof useCollections>);

    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
  });
});
