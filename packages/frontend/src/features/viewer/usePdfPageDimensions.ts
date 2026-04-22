import { useEffect, useRef } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';

interface UsePdfPageDimensionsOptions {
    pdfDocument: PDFDocumentProxy | null;
    enabled?: boolean;
}

/**
 * Preloads all page dimensions when a PDF document loads.
 * Stores base dimensions (scale=1.0) in the pdfViewerStore.
 * Scaled dimensions are computed on-the-fly based on current zoom.
 */
export function usePdfPageDimensions({
    pdfDocument,
    enabled = true,
}: UsePdfPageDimensionsOptions): void {
    const setPageDimensionsBulk = usePdfViewerStore(s => s.setPageDimensionsBulk);
    const clearPageDimensions = usePdfViewerStore(s => s.clearPageDimensions);
    const isCancelledRef = useRef(false);

    useEffect(() => {
        if (!pdfDocument || !enabled) {
            return;
        }

        // Clear previous dimensions when document changes
        clearPageDimensions();

        const preloadDimensions = async () => {
            try {
                const dimensions = new Map<number, { baseWidth: number; baseHeight: number }>();
                const numPages = pdfDocument.numPages;

                // Fetch dimensions for all pages
                for (let pageNum = 1; pageNum <= numPages; pageNum++) {
                    if (isCancelledRef.current) return;

                    const page = await pdfDocument.getPage(pageNum);
                    const viewport = page.getViewport({ scale: 1.0 });

                    dimensions.set(pageNum, {
                        baseWidth: viewport.width,
                        baseHeight: viewport.height,
                    });
                }

                if (!isCancelledRef.current) {
                    setPageDimensionsBulk(dimensions);
                }
            } catch (error) {
                console.error('Failed to preload page dimensions:', error);
            }
        };

        preloadDimensions();

        return () => {
            isCancelledRef.current = true;
        };
    }, [pdfDocument, enabled, clearPageDimensions, setPageDimensionsBulk]);
}
