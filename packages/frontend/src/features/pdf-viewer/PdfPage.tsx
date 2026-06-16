import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import { useNewPdfViewerStore } from './pdfViewerStore';
import { PdfCanvasLayer } from './PdfCanvasLayer';
import { PdfTextLayer } from './PdfTextLayer';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import { PdfSelectionLayer } from './PdfSelectionLayer';
import { PdfAnnotationLayer } from './PdfAnnotationLayer';
import { PdfChatHighlightLayer } from './PdfChatHighlightLayer';
import {
  DEFAULT_PAGE_DIMENSIONS,
  getPageDimensionsFromViewport,
  getScaledPageSize,
  hasSameDimensions,
  type PageDimensions,
} from './pdfPageLayout';

interface PdfPageProps {
  pdfDocument: PDFDocumentProxy;
  pageNumber: number;
  pdfId: string;
  estimatedDimensions?: PageDimensions;
}

/**
 * Wraps a single PDF page with all render layers:
 *
 *   z‑order (bottom → top):
 *   1. Canvas (rendered PDF page image)
 *   2. Text layer (selectable transparent text)
 *   3. Selection overlay (visible highlight rects on text selection)
 *   4. Chat highlight overlay (temporary snippet highlights)
 *   5. Annotation overlay (highlights, rects, notes, interactions)
 *
 * Plus IntersectionObserver‑based virtualization.
 */
export const PdfPage = ({
  pdfDocument,
  pageNumber,
  pdfId,
  estimatedDimensions,
}: PdfPageProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const textLayerHandleRef = useRef<PdfTextLayerHandle>(null);
  const [canvasVisible, setCanvasVisible] = useState(false);
  const [pageProxy, setPageProxy] = useState<PDFPageProxy | null>(null);
  const [textRenderId, setTextRenderId] = useState(0);

  const zoom = useNewPdfViewerStore((s) => s.zoom);
  const rotation = useNewPdfViewerStore((s) => s.rotation);
  const dimensions = useNewPdfViewerStore((s) =>
    s.pageDimensions.get(pageNumber),
  );
  const setPageDimensions = useNewPdfViewerStore((s) => s.setPageDimensions);

  // ---- Load page proxy (shared between canvas and text layer) ----
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const page = await pdfDocument.getPage(pageNumber);
        if (!cancelled) {
          const nextDimensions = getPageDimensionsFromViewport(
            page.getViewport({ scale: 1.0 }),
          );
          const currentDimensions =
            useNewPdfViewerStore.getState().pageDimensions.get(pageNumber);

          setPageProxy(page);
          if (!hasSameDimensions(currentDimensions, nextDimensions)) {
            setPageDimensions(pageNumber, nextDimensions);
          }
        }
      } catch (error) {
        console.error(`Failed to load page ${pageNumber}`, error);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfDocument, pageNumber, setPageDimensions]);

  // ---- IntersectionObserver for canvas virtualisation ----
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setCanvasVisible(true);
        } else {
          setCanvasVisible(false);
        }
      },
      {
        rootMargin: '150% 0px 150% 0px',
        threshold: 0,
      },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [pageNumber]);

  // Scaled placeholder size
  const activeDimensions =
    dimensions ?? estimatedDimensions ?? DEFAULT_PAGE_DIMENSIONS;
  const { width: w, height: h } = getScaledPageSize(
    activeDimensions,
    zoom,
    rotation,
  );

  return (
    <div
      ref={ref}
      id={`pdf-page-${pageNumber}`}
      className="flex justify-center mb-6 w-max min-w-full"
      data-page-number={pageNumber}
    >
      <div
        className="relative inline-block bg-white shadow-md mx-auto transition-all duration-200"
        style={{ width: `${w}px`, height: `${h}px` }}
      >
        {canvasVisible ? (
          <PdfCanvasLayer pdfDocument={pdfDocument} pageNumber={pageNumber} />
        ) : (
          <div
            className="bg-white shadow-sm flex items-center justify-center border
                       text-muted-foreground/30 text-2xl font-bold select-none"
            style={{ width: `${w}px`, height: `${h}px` }}
            aria-label={`Page ${pageNumber} placeholder`}
          >
            {pageNumber}
          </div>
        )}

        {/* Interaction layers (only when canvas is visible) */}
        {canvasVisible && (
          <>
            <PdfTextLayer
              ref={textLayerHandleRef}
              pageProxy={pageProxy}
              onRenderComplete={setTextRenderId}
            />
            <PdfSelectionLayer
              textLayerRef={textLayerHandleRef}
              pageNumber={pageNumber}
            />
            <PdfChatHighlightLayer
              pdfId={pdfId}
              pageNumber={pageNumber}
              textLayerRef={textLayerHandleRef}
            />
            <PdfAnnotationLayer
              pageNumber={pageNumber}
              pdfId={pdfId}
              textLayerRef={textLayerHandleRef}
              renderId={textRenderId}
            />
          </>
        )}
      </div>
    </div>
  );
};
