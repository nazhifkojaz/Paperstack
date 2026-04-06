import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { TextLayer, type TextLayerHandle } from './TextLayer';
import { AnnotationOverlay } from '../annotations/AnnotationOverlay';

interface PdfCanvasProps {
    pdfDocument: PDFDocumentProxy | null;
    pageNumber: number;
    pdfId: string;
    className?: string;
}

export const PdfCanvas = ({ pdfDocument, pageNumber, pdfId, className = '' }: PdfCanvasProps) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const textLayerHandleRef = useRef<TextLayerHandle>(null);
    const { zoom, rotation } = usePdfViewerStore();
    const [pageProxy, setPageProxy] = useState<PDFPageProxy | null>(null);
    const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

    // Load the requested page
    useEffect(() => {
        if (!pdfDocument) return;

        let isMounted = true;

        const loadPage = async () => {
            try {
                const page = await pdfDocument.getPage(pageNumber);
                if (isMounted) {
                    setPageProxy(page);
                }
            } catch (error) {
                console.error('Failed to load page', error);
            }
        };

        loadPage();

        return () => {
            isMounted = false;
        };
    }, [pdfDocument, pageNumber]);

    // Render the page
    useEffect(() => {
        if (!pageProxy || !canvasRef.current || !containerRef.current) return;

        const canvas = canvasRef.current;
        const context = canvas.getContext('2d');
        if (!context) return;

        // Use higher scale for better resolution on high-DPI screens
        const DPR = window.devicePixelRatio || 1;

        // Apply zoom
        const viewport = pageProxy.getViewport({ scale: zoom, rotation });

        // Set actual size in memory (scaled for HiDPI)
        canvas.width = viewport.width * DPR;
        canvas.height = viewport.height * DPR;

        // Set display size
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;

        // Scale context to match HiDPI
        context.scale(DPR, DPR);

        // Cancel any ongoing render task
        if (renderTaskRef.current) {
            renderTaskRef.current.cancel();
        }

        const renderContext = {
            canvasContext: context,
            viewport: viewport,
            canvas,
        };

        const renderTask = pageProxy.render(renderContext);
        renderTaskRef.current = renderTask;

        renderTask.promise.catch((error) => {
            if (error.name === 'RenderingCancelledException') {
                // Expected behavior when re-rendering quickly
                return;
            }
            console.error('Render error', error);
        });

        return () => {
            if (renderTaskRef.current) {
                renderTaskRef.current.cancel();
            }
        };
    }, [pageProxy, zoom, rotation]);

    return (
        <div
            ref={containerRef}
            className={`relative inline-block bg-white shadow-md mx-auto my-4 transition-all duration-200 ${className}`}
        >
            <canvas ref={canvasRef} className="block" />
            <TextLayer ref={textLayerHandleRef} pageProxy={pageProxy} />
            <AnnotationOverlay pageNumber={pageNumber} pdfId={pdfId} textLayerHandle={textLayerHandleRef} />
        </div>
    );
};
