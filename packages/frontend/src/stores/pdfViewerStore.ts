import { create } from 'zustand';

export interface PageDimensions {
    baseWidth: number;
    baseHeight: number;
}

interface PdfViewerState {
    currentPage: number;
    totalPages: number;
    zoom: number;
    rotation: number;

    // Page dimension caching
    pageDimensions: Map<number, PageDimensions>;
    isDimensionsLoading: boolean;

    // Actions
    setCurrentPage: (page: number) => void;
    setTotalPages: (total: number) => void;
    setZoom: (zoom: number | ((prev: number) => number)) => void;
    setRotation: (rotation: number | ((prev: number) => number)) => void;
    reset: () => void;

    // Page dimension actions
    setPageDimensions: (pageNum: number, dimensions: PageDimensions) => void;
    setPageDimensionsBulk: (dimensions: Map<number, PageDimensions>) => void;
    getScaledDimensions: (pageNum: number) => { width: number; height: number } | null;
    clearPageDimensions: () => void;
}

const initialState = {
    currentPage: 1,
    totalPages: 0,
    zoom: 1.0,
    rotation: 0,
    pageDimensions: new Map<number, PageDimensions>(),
    isDimensionsLoading: true,
};

export const usePdfViewerStore = create<PdfViewerState>((set, get) => ({
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

    // Page dimension actions
    setPageDimensions: (pageNum, dimensions) => set((state) => ({
        pageDimensions: new Map(state.pageDimensions).set(pageNum, dimensions),
    })),

    setPageDimensionsBulk: (dimensions) => set({ pageDimensions: dimensions }),

    getScaledDimensions: (pageNum) => {
        const state = get();
        const dimensions = state.pageDimensions.get(pageNum);
        if (!dimensions) return null;
        return {
            width: dimensions.baseWidth * state.zoom,
            height: dimensions.baseHeight * state.zoom,
        };
    },

    clearPageDimensions: () => set({
        pageDimensions: new Map<number, PageDimensions>(),
        isDimensionsLoading: true,
    }),
}));
