import { create } from 'zustand';
import type { PdfViewerState, PdfViewerRotation, PdfViewerZoomMode } from './pdfViewerTypes';
import type { PageDimensions } from './pdfPageLayout';

// ---------------------------------------------------------------------------
// Internal: page‑dimension cache (not part of the public PdfViewerState type)
// ---------------------------------------------------------------------------

interface NewPdfViewerStore extends PdfViewerState {
  // ---- Dimension cache ----
  pageDimensions: Map<number, PageDimensions>;

  // ---- Passive visibility ----
  setVisiblePage: (page: number) => void;

  // ---- Explicit navigation ----
  /** Sets targetPage so the scroll container will jump. Caller must clear after. */
  jumpToPage: (page: number) => void;
  /** Clears targetPage (call after scroll completes). */
  clearTargetPage: () => void;

  // ---- Page count ----
  setTotalPages: (total: number) => void;

  // ---- Zoom ----
  setZoom: (zoom: number | ((prev: number) => number)) => void;
  setZoomMode: (mode: PdfViewerZoomMode) => void;

  // ---- Rotation ----
  setRotation: (rotation: PdfViewerRotation | ((prev: PdfViewerRotation) => PdfViewerRotation)) => void;

  // ---- Dimensions ----
  setPageDimensions: (pageNum: number, dims: PageDimensions) => void;
  clearPageDimensions: () => void;

  // ---- Lifecycle ----
  reset: () => void;
}

const initialState: PdfViewerState & {
  pageDimensions: Map<number, PageDimensions>;
} = {
  visiblePage: 1,
  targetPage: null,
  totalPages: 0,
  zoom: 1.0,
  zoomMode: 'manual' as PdfViewerZoomMode,
  rotation: 0 as PdfViewerRotation,
  pageDimensions: new Map<number, PageDimensions>(),
};

export const useNewPdfViewerStore = create<NewPdfViewerStore>((set) => ({
  ...initialState,

  // ---- Passive visibility (MUST NOT trigger scrolling) ----
  setVisiblePage: (page) => set({ visiblePage: page }),

  // ---- Explicit navigation ----
  jumpToPage: (page) => set({ targetPage: page }),
  clearTargetPage: () => set({ targetPage: null }),

  // ---- Page count ----
  setTotalPages: (total) => set({ totalPages: total }),

  // ---- Zoom ----
  setZoom: (zoom) =>
    set((state) => ({
      zoom: typeof zoom === 'function' ? zoom(state.zoom) : zoom,
    })),

  setZoomMode: (mode) => set({ zoomMode: mode }),

  // ---- Rotation ----
  setRotation: (rotation) =>
    set((state) => ({
      rotation:
        typeof rotation === 'function'
          ? rotation(state.rotation as PdfViewerRotation)
          : rotation,
    })),

  // ---- Dimensions ----
  setPageDimensions: (pageNum, dims) =>
    set((state) => {
      const next = new Map(state.pageDimensions);
      next.set(pageNum, dims);
      return { pageDimensions: next };
    }),

  clearPageDimensions: () =>
    set({
      pageDimensions: new Map<number, PageDimensions>(),
    }),

  // ---- Lifecycle ----
  reset: () => set({ ...initialState, pageDimensions: new Map() }),
}));
