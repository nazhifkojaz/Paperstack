import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { PdfCanvas } from './PdfCanvas';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';

interface VirtualPdfPageProps {
    pdfDocument: PDFDocumentProxy;
    pageNumber: number;
    pdfId: string;
}

export const VirtualPdfPage = ({ pdfDocument, pageNumber, pdfId }: VirtualPdfPageProps) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [isVisible, setIsVisible] = useState(false);
    const { setCurrentPage } = usePdfViewerStore();

    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setIsVisible(true);
                        if (entry.intersectionRatio > 0.5) {
                            setCurrentPage(pageNumber);
                        }
                    } else {
                        setIsVisible(false);
                    }
                });
            },
            {
                rootMargin: '150% 0px 150% 0px', // Pre-render 1.5 viewport heights ahead
                threshold: [0, 0.5, 1.0]
            }
        );

        if (containerRef.current) {
            observer.observe(containerRef.current);
        }

        return () => observer.disconnect();
    }, [pageNumber, setCurrentPage]);

    return (
        <div
            ref={containerRef}
            id={`pdf-page-${pageNumber}`}
            className="w-full flex justify-center mb-6 min-h-[800px] transition-all"
        >
            <div className="relative">
                {isVisible ? (
                    <PdfCanvas pdfDocument={pdfDocument} pageNumber={pageNumber} pdfId={pdfId} />
                ) : (
                    <div className="bg-white shadow-sm w-[600px] h-[800px] animate-pulse flex items-center justify-center border text-muted-foreground/30 text-2xl font-bold">
                        {pageNumber}
                    </div>
                )}
            </div>
        </div>
    );
};
