import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { pdfjsLib } from '@/lib/pdfjs';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { usePdf } from '@/api/pdfs';
import { usePdfSource } from '@/features/viewer/usePdfSource';
import { useNewPdfViewerStore } from './pdfViewerStore';
import { PdfPage } from './PdfPage';
import { Loader2 } from 'lucide-react';
import {
  buildPdfPageLayout,
  getBasePageWidthForRotation,
  getEstimatedPageDimensions,
  getPageDimensionsFromViewport,
  getPageAtViewportCenter,
  getPdfPageWindow,
  getScrollTopForPage,
  hasSameDimensions,
} from './pdfPageLayout';

interface PdfViewerProps {
  pdfId: string;
  /** Pre‑loaded PDF document.  When provided, internal loading is skipped. */
  pdfDocument?: PDFDocumentProxy | null;
  /** Error message from external loader (shown when pdfDocument is null). */
  loadError?: string | null;
  /** Whether external metadata/content is still loading. */
  isLoading?: boolean;
}

const ZOOM_ANCHOR_RESTORE_DELAY = 150;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 5.0;
const TARGET_PAGE_JUMP_CLEAR_DELAY = 250;

export const PdfViewer = ({
  pdfId,
  pdfDocument: externalDoc,
  loadError: externalLoadError,
  isLoading: externalLoading,
}: PdfViewerProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const zoomAnchorRef = useRef<{
    pageCenter: number;
    ratioY: number;
  } | null>(null);
  const isZoomingRef = useRef(false);
  const [viewport, setViewport] = useState({ scrollTop: 0, height: 0 });

  // Internal document state (used only when no external doc provided)
  const [internalDoc, setInternalDoc] =
    useState<PDFDocumentProxy | null>(null);
  const [internalLoadError, setInternalLoadError] = useState<string | null>(
    null,
  );

  const pdfDocument = externalDoc !== undefined ? externalDoc : internalDoc;

  const usingExternal = externalDoc !== undefined;

  const totalPages = useNewPdfViewerStore((s) => s.totalPages);
  const visiblePage = useNewPdfViewerStore((s) => s.visiblePage);
  const targetPage = useNewPdfViewerStore((s) => s.targetPage);
  const zoom = useNewPdfViewerStore((s) => s.zoom);
  const zoomMode = useNewPdfViewerStore((s) => s.zoomMode);
  const rotation = useNewPdfViewerStore((s) => s.rotation);
  const pageDimensions = useNewPdfViewerStore((s) => s.pageDimensions);
  const setTotalPages = useNewPdfViewerStore((s) => s.setTotalPages);
  const setVisiblePage = useNewPdfViewerStore((s) => s.setVisiblePage);
  const setZoom = useNewPdfViewerStore((s) => s.setZoom);
  const clearTargetPage = useNewPdfViewerStore((s) => s.clearTargetPage);
  const setPageDimensions = useNewPdfViewerStore((s) => s.setPageDimensions);
  const clearPageDimensions = useNewPdfViewerStore(
    (s) => s.clearPageDimensions,
  );
  const reset = useNewPdfViewerStore((s) => s.reset);

  // ---- Internal document loading (only when no external doc) ----
  const { data: pdfMetadata, isLoading: isLoadingMeta } = usePdf(
    usingExternal ? '' : pdfId,
  );
  const {
    blob,
    sourceUrl,
    isLoading: isLoadingContent,
    error,
    isLinked,
  } = usePdfSource(usingExternal ? undefined : pdfMetadata);

  useEffect(() => {
    reset();
    return () => reset();
  }, [reset]);

  useEffect(() => {
    if (usingExternal) return;
    if (isLinked && !sourceUrl) return;
    if (!isLinked && !blob) return;

    let cancelled = false;

    (async () => {
      try {
        if (cancelled) return;
        setInternalLoadError(null);

        let doc: PDFDocumentProxy;
        if (isLinked && sourceUrl) {
          doc = await pdfjsLib.getDocument({ url: sourceUrl }).promise;
        } else if (blob) {
          const buffer = await blob.arrayBuffer();
          doc = await pdfjsLib.getDocument({
            data: new Uint8Array(buffer),
          }).promise;
        } else {
          return;
        }

        if (!cancelled) {
          setInternalDoc(doc);
          setTotalPages(doc.numPages);
        }
      } catch (err) {
        console.error('Error loading PDF document:', err);
        if (!cancelled) {
          setInternalLoadError(
            err instanceof Error ? err.message : 'Failed to load PDF',
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [blob, sourceUrl, isLinked, setTotalPages, usingExternal]);

  // ---- Sync totalPages from external doc ----
  useEffect(() => {
    if (usingExternal && externalDoc) {
      setTotalPages(externalDoc.numPages);
    }
  }, [usingExternal, externalDoc, setTotalPages]);

  // ---- Seed first-page dimensions for early layout estimates ----
  useEffect(() => {
    if (!pdfDocument) return;

    let cancelled = false;
    clearPageDimensions();

    (async () => {
      try {
        const page = await pdfDocument.getPage(1);
        if (cancelled) return;

        const nextDimensions = getPageDimensionsFromViewport(
          page.getViewport({ scale: 1.0 }),
        );
        const currentDimensions =
          useNewPdfViewerStore.getState().pageDimensions.get(1);

        if (!hasSameDimensions(currentDimensions, nextDimensions)) {
          setPageDimensions(1, nextDimensions);
        }
      } catch (err) {
        console.error('Failed to load first page dimensions:', err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfDocument, setPageDimensions, clearPageDimensions]);

  const pageLayout = useMemo(
    () =>
      buildPdfPageLayout({
        totalPages,
        pageDimensions,
        zoom,
        rotation,
      }),
    [totalPages, pageDimensions, zoom, rotation],
  );

  const visiblePageLayouts = useMemo(
    () =>
      getPdfPageWindow({
        pages: pageLayout.pages,
        scrollTop: viewport.scrollTop,
        viewportHeight: viewport.height,
      }),
    [pageLayout.pages, viewport.scrollTop, viewport.height],
  );

  const firstVisibleLayout = visiblePageLayouts[0];
  const lastVisibleLayout =
    visiblePageLayouts[visiblePageLayouts.length - 1];
  const topSpacerHeight = firstVisibleLayout?.top ?? 0;
  const bottomSpacerHeight = lastVisibleLayout
    ? Math.max(
        0,
        pageLayout.totalHeight -
          (lastVisibleLayout.top + lastVisibleLayout.itemHeight),
      )
    : 0;

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    let animationFrame: number | null = null;
    const updateViewport = () => {
      const nextViewport = {
        scrollTop: container.scrollTop,
        height: container.clientHeight,
      };
      setViewport((currentViewport) => {
        if (
          currentViewport.scrollTop === nextViewport.scrollTop &&
          currentViewport.height === nextViewport.height
        ) {
          return currentViewport;
        }
        return nextViewport;
      });
    };
    const scheduleUpdate = () => {
      if (animationFrame !== null) return;
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = null;
        updateViewport();
      });
    };

    updateViewport();
    container.addEventListener('scroll', scheduleUpdate, { passive: true });

    const resizeObserver = new ResizeObserver(scheduleUpdate);
    resizeObserver.observe(container);

    return () => {
      if (animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
      }
      resizeObserver.disconnect();
      container.removeEventListener('scroll', scheduleUpdate);
    };
  }, [pdfDocument, totalPages]);

  // ---- Fit-width zoom mode ----
  useEffect(() => {
    if (zoomMode !== 'fit-width') return;

    const container = scrollRef.current;
    if (!container) return;

    const applyFitWidth = () => {
      const state = useNewPdfViewerStore.getState();
      const dims = getEstimatedPageDimensions(
        state.pageDimensions,
        state.visiblePage,
      );

      const style = window.getComputedStyle(container);
      const horizontalPadding =
        Number.parseFloat(style.paddingLeft || '0') +
        Number.parseFloat(style.paddingRight || '0');
      const availableWidth = Math.max(0, container.clientWidth - horizontalPadding);
      const baseWidth = getBasePageWidthForRotation(dims, state.rotation);

      if (availableWidth <= 0 || baseWidth <= 0) return;
      const nextZoom = Math.max(
        MIN_ZOOM,
        Math.min(MAX_ZOOM, availableWidth / baseWidth),
      );
      setZoom(nextZoom);
    };

    applyFitWidth();
    const resizeObserver = new ResizeObserver(applyFitWidth);
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [zoomMode, visiblePage, rotation, pageDimensions, setZoom]);

  // ---- Passive visible-page tracking ----
  useEffect(() => {
    const nextVisiblePage = getPageAtViewportCenter({
      pages: pageLayout.pages,
      scrollTop: viewport.scrollTop,
      viewportHeight: viewport.height,
    });

    if (nextVisiblePage !== visiblePage) {
      setVisiblePage(nextVisiblePage);
    }
  }, [
    pageLayout.pages,
    setVisiblePage,
    viewport.scrollTop,
    viewport.height,
    visiblePage,
  ]);

  // ---- Explicit page jumps ----
  useEffect(() => {
    if (targetPage === null) return;

    const container = scrollRef.current;
    const targetLayout = pageLayout.pages[targetPage - 1];
    if (!container || !targetLayout) {
      clearTargetPage();
      return;
    }

    const el = document.getElementById(`pdf-page-${targetPage}`);
    if (el) {
      const rect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const fullyVisible =
        rect.top >= containerRect.top && rect.bottom <= containerRect.bottom;
      const mostlyVisible =
        rect.top >= containerRect.top - rect.height * 0.3 &&
        rect.bottom <= containerRect.bottom + rect.height * 0.3;

      if (fullyVisible || mostlyVisible) {
        clearTargetPage();
        return;
      }
    }

    container.scrollTo({ top: targetLayout.top, behavior: 'smooth' });
    setVisiblePage(targetPage);
    const timer = setTimeout(
      () => clearTargetPage(),
      TARGET_PAGE_JUMP_CLEAR_DELAY,
    );
    return () => clearTimeout(timer);
  }, [targetPage, pageLayout.pages, clearTargetPage, setVisiblePage]);

  // ---- Scroll-anchor preservation on zoom ----
  const saveZoomAnchor = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;

    const viewCenter = container.scrollTop + container.clientHeight / 2;
    const centeredPage = pageLayout.pages.find(
      (page) =>
        viewCenter >= page.top && viewCenter < page.top + page.itemHeight,
    );

    if (!centeredPage) {
      zoomAnchorRef.current = { pageCenter: visiblePage, ratioY: 0.3 };
      return;
    }

    const ratioY =
      centeredPage.height > 0
        ? (viewCenter - centeredPage.top) / centeredPage.height
        : 0.5;
    zoomAnchorRef.current = {
      pageCenter: centeredPage.pageNumber,
      ratioY: Math.max(0, Math.min(1, ratioY)),
    };
  }, [pageLayout.pages, visiblePage]);

  useEffect(
    () =>
      useNewPdfViewerStore.subscribe((state, previousState) => {
        if (state.zoom === previousState.zoom) return;
        saveZoomAnchor();
        isZoomingRef.current = true;
      }),
    [saveZoomAnchor],
  );

  useEffect(() => {
    if (!isZoomingRef.current || !zoomAnchorRef.current) return;
    isZoomingRef.current = false;

    const anchor = zoomAnchorRef.current;
    const timer = setTimeout(() => {
      const container = scrollRef.current;
      const anchorLayout = pageLayout.pages[anchor.pageCenter - 1];
      if (!container || !anchorLayout) {
        zoomAnchorRef.current = null;
        return;
      }

      container.scrollTo({
        top: getScrollTopForPage(
          anchorLayout,
          container.clientHeight,
          anchor.ratioY,
        ),
        behavior: 'auto',
      });
      zoomAnchorRef.current = null;
    }, ZOOM_ANCHOR_RESTORE_DELAY);

    return () => clearTimeout(timer);
  }, [zoom, pageLayout.pages]);

  const isLoading = usingExternal
    ? externalLoading
    : isLoadingMeta || isLoadingContent;

  const hasError = usingExternal
    ? externalLoadError
    : error || internalLoadError;

  // ---- Loading state ----
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-muted/20">
        <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Loading document…</p>
      </div>
    );
  }

  // ---- Error state ----
  if (hasError) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-muted/20 p-8">
        <div className="bg-destructive/10 text-destructive p-6 rounded-xl text-center max-w-md">
          <h2 className="text-xl font-bold mb-2">Failed to load PDF</h2>
          <p className="mb-2">
            {hasError instanceof Error ? hasError.message : hasError || 'Document not found'}
          </p>
        </div>
      </div>
    );
  }

  // ---- Empty document ----
  if (!pdfDocument || totalPages === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
      </div>
    );
  }

  // ---- Render ----
  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-auto custom-scrollbar bg-neutral-100 dark:bg-neutral-900 p-4 md:p-8"
    >
      <div className="flex flex-col w-full">
        <div style={{ height: `${topSpacerHeight}px` }} />
        {visiblePageLayouts.map((page) => (
          <PdfPage
            key={page.pageNumber}
            pdfDocument={pdfDocument}
            pageNumber={page.pageNumber}
            pdfId={pdfId}
            estimatedDimensions={page.dimensions}
          />
        ))}
        <div style={{ height: `${bottomSpacerHeight}px` }} />
      </div>
    </div>
  );
};
