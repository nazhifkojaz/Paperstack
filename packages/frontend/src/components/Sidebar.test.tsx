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
  const mockLibraryStore = useLibraryStore as ReturnType<typeof vi.mock>;
  const mockUseCollections = useCollections as ReturnType<typeof vi.mock>;
  const mockUseCreateCollection = useCreateCollection as ReturnType<typeof vi.mock>;

  beforeEach(() => {
    vi.clearAllMocks();

    mockLibraryStore.mockReturnValue({
      selectedProjectId: null,
      setSelectedProjectId: vi.fn(),
      resetFilters: vi.fn(),
    });

    mockUseCollections.mockReturnValue({ data: [] });
    mockUseCreateCollection.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
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
    mockUseCollections.mockReturnValue({ data: mockProjects });

    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('Research Paper')).toBeInTheDocument();
  });

  it('shows empty state when no projects exist', () => {
    mockUseCollections.mockReturnValue({ data: [] });

    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
  });
});
