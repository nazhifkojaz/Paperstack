import { create } from 'zustand';

interface LibraryState {
    viewMode: 'grid' | 'list';
    searchQuery: string;
    selectedProjectId: string | null;
    sortOption: string;
    isDeepSearch: boolean;

    // Selection
    isSelectionMode: boolean;
    selectedPdfIds: Set<string>;

    // Actions
    setViewMode: (mode: 'grid' | 'list') => void;
    setSearchQuery: (query: string) => void;
    setSelectedProjectId: (id: string | null) => void;
    setSortOption: (option: string) => void;
    setDeepSearch: (v: boolean) => void;
    resetFilters: () => void;

    // Selection
    setSelectionMode: (active: boolean) => void;
    togglePdfSelection: (pdfId: string) => void;
    selectAllVisible: (pdfIds: string[]) => void;
    clearSelection: () => void;
}

export const useLibraryStore = create<LibraryState>((set) => ({
    viewMode: 'grid',
    searchQuery: '',
    selectedProjectId: null,
    sortOption: '-uploaded_at',
    isDeepSearch: false,

    // Selection
    isSelectionMode: false,
    selectedPdfIds: new Set(),

    setViewMode: (mode) => set({ viewMode: mode }),
    setSearchQuery: (query) => set({ searchQuery: query }),
    setSelectedProjectId: (id) => set({ selectedProjectId: id }),
    setSortOption: (option) => set({ sortOption: option }),
    setDeepSearch: (v) => set({ isDeepSearch: v }),
    resetFilters: () => set({
        searchQuery: '',
        selectedProjectId: null,
        sortOption: '-uploaded_at',
        isDeepSearch: false,
    }),

    // Selection
    setSelectionMode: (active) => set({
        isSelectionMode: active,
        selectedPdfIds: new Set(),
    }),
    togglePdfSelection: (pdfId) => set((state) => {
        const newSelection = new Set(state.selectedPdfIds);
        if (newSelection.has(pdfId)) {
            newSelection.delete(pdfId);
        } else {
            newSelection.add(pdfId);
        }
        return { selectedPdfIds: newSelection };
    }),
    selectAllVisible: (pdfIds) => set({ selectedPdfIds: new Set(pdfIds) }),
    clearSelection: () => set({ selectedPdfIds: new Set() }),
}));
