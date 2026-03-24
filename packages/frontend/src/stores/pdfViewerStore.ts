import { create } from 'zustand';

interface PdfViewerState {
    currentPage: number;
    totalPages: number;
    zoom: number;
    rotation: number;

    // Actions
    setCurrentPage: (page: number) => void;
    setTotalPages: (total: number) => void;
    setZoom: (zoom: number | ((prev: number) => number)) => void;
    setRotation: (rotation: number | ((prev: number) => number)) => void;
    reset: () => void;
}

const initialState = {
    currentPage: 1,
    totalPages: 0,
    zoom: 1.0,
    rotation: 0,
};

export const usePdfViewerStore = create<PdfViewerState>((set) => ({
    ...initialState,

    setCurrentPage: (page) => set({ currentPage: page }),
    setTotalPages: (total) => set({ totalPages: total }),

    setZoom: (zoom) => set((state) => ({
        zoom: typeof zoom === 'function' ? zoom(state.zoom) : zoom
    })),

    setRotation: (rotation) => set((state) => ({
        rotation: typeof rotation === 'function' ? rotation(state.rotation) : rotation
    })),

    reset: () => set(initialState),
}));
