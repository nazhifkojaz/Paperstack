import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Sidebar } from './Sidebar';
import { useLibraryStore } from '@/stores/libraryStore';
import { useCollections, useCreateCollection, useUpdateCollection, useDeleteCollection, useExportCollection, useSwapCollectionPositions } from '@/api/collections';
import { MemoryRouter } from 'react-router-dom';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockNavigate = vi.hoisted(() => vi.fn());

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/stores/libraryStore');
vi.mock('@/api/collections');

describe('Sidebar', () => {
  const mockLibraryStore = vi.mocked(useLibraryStore);
  const mockUseCollections = vi.mocked(useCollections);
  const mockUseCreateCollection = vi.mocked(useCreateCollection);
  const mockUseUpdateCollection = vi.mocked(useUpdateCollection);
  const mockUseSwapCollectionPositions = vi.mocked(useSwapCollectionPositions);
  const mockUseDeleteCollection = vi.mocked(useDeleteCollection);
  const mockUseExportCollection = vi.mocked(useExportCollection);
  const resetFilters = vi.fn();
  const swapPositions = vi.fn();
  const deleteCollection = vi.fn();

  const projects = [
    { id: '1', name: 'First', user_id: 'u1', parent_id: null, position: 0, created_at: '' },
    { id: '2', name: 'Second', user_id: 'u1', parent_id: null, position: 1, created_at: '' },
  ];

  function renderAt(route: string) {
    return render(
      <MemoryRouter initialEntries={[route]}>
        <Sidebar />
      </MemoryRouter>
    );
  }

  function openMenu(projectName: string) {
    const projectButton = screen.getByRole('button', { name: projectName });
    const row = projectButton.closest('.group');
    if (!(row instanceof HTMLElement)) throw new Error(`Missing row for ${projectName}`);
    fireEvent.pointerDown(within(row).getByTitle('More options'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
  }

  async function confirmDelete(projectName: string) {
    openMenu(projectName);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    const dialog = await screen.findByRole('dialog');
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();

    mockLibraryStore.mockReturnValue({
      selectedProjectId: null,
      setSelectedProjectId: vi.fn(),
      resetFilters,
    });

    mockUseCollections.mockReturnValue({ data: [] } as unknown as ReturnType<typeof useCollections>);
    mockUseCreateCollection.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as unknown as ReturnType<typeof useCreateCollection>);
    mockUseUpdateCollection.mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false } as unknown as ReturnType<typeof useUpdateCollection>);
    mockUseSwapCollectionPositions.mockReturnValue({ mutateAsync: swapPositions, isPending: false } as unknown as ReturnType<typeof useSwapCollectionPositions>);
    mockUseDeleteCollection.mockReturnValue({ mutateAsync: deleteCollection, isPending: false } as unknown as ReturnType<typeof useDeleteCollection>);
    mockUseExportCollection.mockReturnValue({ mutate: vi.fn(), isPending: false } as unknown as ReturnType<typeof useExportCollection>);
    swapPositions.mockResolvedValue([]);
    deleteCollection.mockResolvedValue(undefined);
  });

  it('renders the sidebar with All Documents button', () => {
    renderAt('/library');

    expect(screen.getByRole('button', { name: /All Documents/i })).toBeInTheDocument();
  });

  it('renders Projects section header', () => {
    renderAt('/library');

    expect(screen.getByText('Projects')).toBeInTheDocument();
  });

  it('renders projects when data is present', () => {
    const mockProjects = [
      { id: '1', name: 'Research Paper', user_id: 'u1', parent_id: null, position: 0, created_at: '' },
    ];
    mockUseCollections.mockReturnValue({ data: mockProjects } as unknown as ReturnType<typeof useCollections>);

    renderAt('/library');

    expect(screen.getByText('Research Paper')).toBeInTheDocument();
  });

  it('shows empty state when no projects exist', () => {
    mockUseCollections.mockReturnValue({ data: [] } as unknown as ReturnType<typeof useCollections>);

    renderAt('/library');

    expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
  });

  it('uses one swap mutation for Move up', async () => {
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library');

    openMenu('Second');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Move up' }));

    await waitFor(() => {
      expect(swapPositions).toHaveBeenCalledOnce();
    });
    expect(swapPositions).toHaveBeenCalledWith({ firstId: '2', secondId: '1' });
  });

  it('uses one swap mutation for Move down', async () => {
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library');

    openMenu('First');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Move down' }));

    await waitFor(() => {
      expect(swapPositions).toHaveBeenCalledOnce();
    });
    expect(swapPositions).toHaveBeenCalledWith({ firstId: '1', secondId: '2' });
  });

  it('keeps rendered ordering when a swap fails', async () => {
    swapPositions.mockRejectedValueOnce(new Error('failed'));
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library');

    openMenu('First');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Move down' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to reorder collection');
    });
    const projectButtons = screen.getAllByRole('button').filter(
      (button) => button.textContent === 'First' || button.textContent === 'Second',
    );
    expect(projectButtons.map((button) => button.textContent)).toEqual(['First', 'Second']);
  });

  it.each([
    '/library/collection/1',
    '/library/collection/1/overview',
    '/chat/collection/1',
  ])('navigates away after deleting the routed collection at %s', async (route) => {
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt(route);

    await confirmDelete('First');

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/library', { replace: true });
    });
    expect(resetFilters).toHaveBeenCalledOnce();
  });

  it('highlights the routed collection on direct overview navigation', () => {
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library/collection/2/overview');

    expect(screen.getByRole('button', { name: 'Second' })).toHaveClass('font-medium');
    expect(screen.getByRole('button', { name: 'First' })).not.toHaveClass('font-medium');
  });

  it('does not navigate when deleting a non-active collection', async () => {
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library/collection/1/overview');

    await confirmDelete('Second');

    await waitFor(() => expect(deleteCollection).toHaveBeenCalledWith('2'));
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(resetFilters).not.toHaveBeenCalled();
  });

  it('navigates after deleting the store-selected collection', async () => {
    mockLibraryStore.mockReturnValue({
      selectedProjectId: '2',
      setSelectedProjectId: vi.fn(),
      resetFilters,
    });
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library');

    await confirmDelete('Second');

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/library', { replace: true });
    });
    expect(resetFilters).toHaveBeenCalledOnce();
  });

  it('does not navigate when deletion fails', async () => {
    deleteCollection.mockRejectedValueOnce(new Error('failed'));
    mockUseCollections.mockReturnValue({ data: projects } as unknown as ReturnType<typeof useCollections>);
    renderAt('/library/collection/1/overview');

    await confirmDelete('First');

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to delete collection');
    });
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(resetFilters).not.toHaveBeenCalled();
  });
});
