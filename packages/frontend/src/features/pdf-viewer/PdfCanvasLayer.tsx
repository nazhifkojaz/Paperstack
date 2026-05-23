import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import { useNewPdfViewerStore } from './pdfViewerStore';

interface PdfCanvasLayerProps {
  pdfDocument: PDFDocumentProxy;
  pageNumber: number;
}

/** Renders a single PDF page to a canvas. Handles zoom, rotation, DPR, and
 *  cancels in-flight render tasks on re-render. No text layer, no annotations. */
export const PdfCanvasLayer = ({ pdfDocument, pageNumber }: PdfCanvasLayerProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const [pageProxy, setPageProxy] = useState<PDFPageProxy | null>(null);

  const zoom = useNewPdfViewerStore((s) => s.zoom);
  const rotation = useNewPdfViewerStore((s) => s.rotation);

  // Load the requested page proxy
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const page = await pdfDocument.getPage(pageNumber);
        if (!cancelled) setPageProxy(page);
      } catch (error) {
        console.error(`Failed to load page ${pageNumber}`, error);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfDocument, pageNumber]);

  // Render page to canvas whenever proxy, zoom, or rotation change
  useEffect(() => {
    if (!pageProxy || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const viewport = pageProxy.getViewport({ scale: zoom, rotation });

    // Set canvas resolution (physical pixels) and CSS size (logical pixels)
    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Cancel any in-flight render before starting a new one
    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
      renderTaskRef.current = null;
    }

    const task = pageProxy.render({
      canvasContext: ctx,
      viewport,
      canvas,
    });
    renderTaskRef.current = task;

    task.promise.catch((error) => {
      if (error?.name === 'RenderingCancelledException') return;
      console.error(`Render error on page ${pageNumber}`, error);
    });

    return () => {
      task.cancel();
      renderTaskRef.current = null;
    };
  }, [pageProxy, zoom, rotation]);

  return <canvas ref={canvasRef} className="block" />;
};
