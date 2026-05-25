/**
 * Tests for pdfViewerStore (new viewer store).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useNewPdfViewerStore } from './pdfViewerStore';

describe('useNewPdfViewerStore', () => {
  beforeEach(() => {
    useNewPdfViewerStore.getState().reset();
  });

  describe('initial state', () => {
    it('visiblePage defaults to 1', () => {
      expect(useNewPdfViewerStore.getState().visiblePage).toBe(1);
    });

    it('targetPage defaults to null', () => {
      expect(useNewPdfViewerStore.getState().targetPage).toBeNull();
    });

    it('totalPages defaults to 0', () => {
      expect(useNewPdfViewerStore.getState().totalPages).toBe(0);
    });

    it('zoom defaults to 1.0', () => {
      expect(useNewPdfViewerStore.getState().zoom).toBe(1.0);
    });

    it('zoomMode defaults to manual', () => {
      expect(useNewPdfViewerStore.getState().zoomMode).toBe('manual');
    });

    it('rotation defaults to 0', () => {
      expect(useNewPdfViewerStore.getState().rotation).toBe(0);
    });
  });

  describe('setVisiblePage', () => {
    it('sets visiblePage', () => {
      useNewPdfViewerStore.getState().setVisiblePage(5);
      expect(useNewPdfViewerStore.getState().visiblePage).toBe(5);
    });

    it('does NOT set targetPage', () => {
      useNewPdfViewerStore.getState().setVisiblePage(5);
      expect(useNewPdfViewerStore.getState().targetPage).toBeNull();
    });

    it('does NOT trigger page jump (flags remain unchanged)', () => {
      const before = useNewPdfViewerStore.getState().targetPage;
      useNewPdfViewerStore.getState().setVisiblePage(42);
      expect(useNewPdfViewerStore.getState().targetPage).toBe(before);
    });
  });

  describe('jumpToPage', () => {
    it('sets targetPage', () => {
      useNewPdfViewerStore.getState().jumpToPage(10);
      expect(useNewPdfViewerStore.getState().targetPage).toBe(10);
    });

    it('does NOT change visiblePage', () => {
      useNewPdfViewerStore.getState().setVisiblePage(3);
      useNewPdfViewerStore.getState().jumpToPage(10);
      expect(useNewPdfViewerStore.getState().visiblePage).toBe(3);
    });
  });

  describe('clearTargetPage', () => {
    it('clears targetPage to null', () => {
      useNewPdfViewerStore.getState().jumpToPage(10);
      useNewPdfViewerStore.getState().clearTargetPage();
      expect(useNewPdfViewerStore.getState().targetPage).toBeNull();
    });
  });

  describe('setTotalPages', () => {
    it('sets totalPages', () => {
      useNewPdfViewerStore.getState().setTotalPages(42);
      expect(useNewPdfViewerStore.getState().totalPages).toBe(42);
    });
  });

  describe('setZoom', () => {
    it('sets zoom', () => {
      useNewPdfViewerStore.getState().setZoom(2.0);
      expect(useNewPdfViewerStore.getState().zoom).toBe(2.0);
    });

    it('accepts a function updater', () => {
      useNewPdfViewerStore.getState().setZoom(1.5);
      useNewPdfViewerStore.getState().setZoom((prev) => prev * 2);
      expect(useNewPdfViewerStore.getState().zoom).toBe(3.0);
    });
  });

  describe('setZoomMode', () => {
    it('sets zoomMode', () => {
      useNewPdfViewerStore.getState().setZoomMode('fit-width');
      expect(useNewPdfViewerStore.getState().zoomMode).toBe('fit-width');
    });
  });

  describe('setRotation', () => {
    it('sets rotation', () => {
      useNewPdfViewerStore.getState().setRotation(90);
      expect(useNewPdfViewerStore.getState().rotation).toBe(90);
    });
  });

  describe('pageDimensions', () => {
    it('setPageDimensions stores dimensions for a page', () => {
      useNewPdfViewerStore.getState().setPageDimensions(1, { baseWidth: 612, baseHeight: 792 });
      const dims = useNewPdfViewerStore.getState().pageDimensions.get(1);
      expect(dims?.baseWidth).toBe(612);
      expect(dims?.baseHeight).toBe(792);
    });

    it('getScaledDimensions returns scaled dimensions', () => {
      useNewPdfViewerStore.getState().setPageDimensions(1, { baseWidth: 612, baseHeight: 792 });
      useNewPdfViewerStore.getState().setZoom(2.0);
      const scaled = useNewPdfViewerStore.getState().getScaledDimensions(1);
      expect(scaled?.width).toBeCloseTo(1224);
      expect(scaled?.height).toBeCloseTo(1584);
    });

    it('getScaledDimensions returns null for unknown page', () => {
      expect(useNewPdfViewerStore.getState().getScaledDimensions(999)).toBeNull();
    });

    it('setPageDimensionsBulk replaces all dimensions', () => {
      const map = new Map<number, { baseWidth: number; baseHeight: number }>();
      map.set(1, { baseWidth: 100, baseHeight: 200 });
      map.set(2, { baseWidth: 300, baseHeight: 400 });
      useNewPdfViewerStore.getState().setPageDimensionsBulk(map);
      expect(useNewPdfViewerStore.getState().pageDimensions.size).toBe(2);
    });

    it('clearPageDimensions removes all dimensions', () => {
      useNewPdfViewerStore.getState().setPageDimensions(1, { baseWidth: 100, baseHeight: 100 });
      useNewPdfViewerStore.getState().clearPageDimensions();
      expect(useNewPdfViewerStore.getState().pageDimensions.size).toBe(0);
    });
  });

  describe('reset', () => {
    it('resets all state to initial values', () => {
      useNewPdfViewerStore.getState().setVisiblePage(50);
      useNewPdfViewerStore.getState().jumpToPage(42);
      useNewPdfViewerStore.getState().setTotalPages(100);
      useNewPdfViewerStore.getState().setZoom(3.0);
      useNewPdfViewerStore.getState().reset();

      const s = useNewPdfViewerStore.getState();
      expect(s.visiblePage).toBe(1);
      expect(s.targetPage).toBeNull();
      expect(s.totalPages).toBe(0);
      expect(s.zoom).toBe(1.0);
    });
  });
});
