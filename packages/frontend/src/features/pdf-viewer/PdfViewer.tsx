import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { pdfjsLib } from '@/lib/pdfjs';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { usePdf } from '@/api/pdfs';
import { usePdfSource } from '@/features/viewer/usePdfSource';
import { useNewPdfViewerStore } from './pdfViewerStore';
import { PdfPage } from './PdfPage';
import { Loader2 } from 'lucide-react';

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
  const setPageDimensionsBulk = useNewPdfViewerStore(
    (s) => s.setPageDimensionsBulk,
  );
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

  // ---- Pre‑load page dimensions ----
  useEffect(() => {
    if (!pdfDocument) return;

    let cancelled = false;
    clearPageDimensions();

    (async () => {
      try {
        const dims = new Map<
          number,
          { baseWidth: number; baseHeight: number }
        >();
        for (let p = 1; p <= pdfDocument.numPages; p++) {
          if (cancelled) return;
          const page = await pdfDocument.getPage(p);
          const vp = page.getViewport({ scale: 1.0 });
          dims.set(p, { baseWidth: vp.width, baseHeight: vp.height });
        }
        if (!cancelled) setPageDimensionsBulk(dims);
      } catch (err) {
        console.error('Failed to preload page dimensions:', err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfDocument, setPageDimensionsBulk, clearPageDimensions]);

  // ---- Fit-width zoom mode ----
  useEffect(() => {
    if (zoomMode !== 'fit-width') return;

    const container = scrollRef.current;
    if (!container) return;

    const applyFitWidth = () => {
      const state = useNewPdfViewerStore.getState();
      const dims =
        state.pageDimensions.get(state.visiblePage) ??
        state.pageDimensions.get(1);
      if (!dims) return;

      const style = window.getComputedStyle(container);
      const horizontalPadding =
        Number.parseFloat(style.paddingLeft || '0') +
        Number.parseFloat(style.paddingRight || '0');
      const availableWidth = Math.max(0, container.clientWidth - horizontalPadding);
      const baseWidth =
        state.rotation === 90 || state.rotation === 270
          ? dims.baseHeight
          : dims.baseWidth;

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

  // ---- Passive visible‑page tracking ----
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const pageEls = container.querySelectorAll('[data-page-number]');
    if (pageEls.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        let bestPage = 1;
        let bestRatio = 0;
        for (const entry of entries) {
          if (entry.intersectionRatio > bestRatio) {
            bestRatio = entry.intersectionRatio;
            const pn = Number(
              (entry.target as HTMLElement).dataset.pageNumber,
            );
            if (!isNaN(pn)) bestPage = pn;
          }
        }
        setVisiblePage(bestPage);
      },
      {
        root: container,
        threshold: [0, 0.25, 0.5, 0.75, 1.0],
      },
    );

    for (const el of pageEls) observer.observe(el);
    return () => observer.disconnect();
  }, [totalPages, setVisiblePage, pdfDocument]);

  // ---- Explicit page jumps ----
  useEffect(() => {
    if (targetPage === null) return;

    const container = scrollRef.current;
    const el = document.getElementById(`pdf-page-${targetPage}`);
    if (!container || !el) return;

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

    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const timer = setTimeout(() => clearTargetPage(), 50);
    return () => clearTimeout(timer);
  }, [targetPage, clearTargetPage]);

  // ---- Scroll‑anchor preservation on zoom ----
  const saveZoomAnchor = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;
    const viewTop = container.scrollTop;
    const viewCenter = viewTop + container.clientHeight / 2;

    for (const el of container.querySelectorAll('[data-page-number]')) {
      const elRect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const pageTop =
        elRect.top - containerRect.top + container.scrollTop;
      const pageBottom = pageTop + elRect.height;

      if (viewCenter >= pageTop && viewCenter <= pageBottom) {
        const pn = Number((el as HTMLElement).dataset.pageNumber);
        if (!isNaN(pn)) {
          const ratioY =
            elRect.height > 0
              ? (viewCenter - pageTop) / elRect.height
              : 0.5;
          zoomAnchorRef.current = {
            pageCenter: pn,
            ratioY: Math.max(0, Math.min(1, ratioY)),
          };
          return;
        }
      }
    }

    let bestPn = 1;
    let bestHeight = 0;
    for (const el of container.querySelectorAll('[data-page-number]')) {
      const elRect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const overlap =
        Math.min(elRect.bottom, containerRect.bottom) -
        Math.max(elRect.top, containerRect.top);
      if (overlap > bestHeight) {
        bestHeight = overlap;
        const pn = Number((el as HTMLElement).dataset.pageNumber);
        if (!isNaN(pn)) bestPn = pn;
      }
    }
    zoomAnchorRef.current = { pageCenter: bestPn, ratioY: 0.3 };
  }, []);

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
      const el = document.getElementById(
        `pdf-page-${anchor.pageCenter}`,
      );
      const container = scrollRef.current;
      if (!el || !container) return;

      const elRect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const pageTopInContainer =
        elRect.top - containerRect.top + container.scrollTop;
      const scrollTarget =
        pageTopInContainer +
        anchor.ratioY * elRect.height -
        container.clientHeight / 2;
      container.scrollTo({
        top: Math.max(0, scrollTarget),
        behavior: 'auto',
      });
      zoomAnchorRef.current = null;
    }, ZOOM_ANCHOR_RESTORE_DELAY);

    return () => clearTimeout(timer);
  }, [zoom]);

  const pages = useMemo(
    () => Array.from({ length: totalPages }, (_, i) => i + 1),
    [totalPages],
  );

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
        {pages.map((pageNum) => (
          <PdfPage
            key={pageNum}
            pdfDocument={pdfDocument}
            pageNumber={pageNum}
            pdfId={pdfId}
          />
        ))}
      </div>
    </div>
  );
};
