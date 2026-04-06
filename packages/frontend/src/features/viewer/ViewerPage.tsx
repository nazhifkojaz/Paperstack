import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { pdfjsLib } from '@/lib/pdfjs';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { usePdf } from '@/api/pdfs';
import { usePdfSource } from './usePdfSource';
import { usePdfPageDimensions } from './usePdfPageDimensions';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { ViewerToolbar } from './ViewerToolbar';
import { VirtualPdfPage } from './VirtualPdfPage';
import { AnnotationSidebar } from '../annotations/AnnotationSidebar';
import { CitationPanel } from '../citations/CitationPanel';
import { ChatPanel } from '../chat/ChatPanel';
import { Loader2, ArrowLeft, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ViewerPage() {
    const { pdfId: id } = useParams<{ pdfId: string }>();
    const navigate = useNavigate();
    const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);

    const { currentPage, totalPages, setTotalPages, reset } = usePdfViewerStore();

    // Register global keyboard shortcuts
    useKeyboardShortcuts();

    const { data: pdfMetadata, isLoading: isLoadingMetadata } = usePdf(id!);
    const { blob, sourceUrl, isLoading: isLoadingContent, error, isLinked } = usePdfSource(pdfMetadata);

    // Reset store on mount/unmount
    useEffect(() => {
        reset();
        return () => reset();
    }, [reset]);

    // Load document when content is available
    useEffect(() => {
        if (isLinked && !sourceUrl) return;
        if (!isLinked && !blob) return;

        let isMounted = true;

        const loadPdf = async () => {
            try {
                // Clear previous error at start of new load attempt
                if (isMounted) setLoadError(null);
                let doc: PDFDocumentProxy;

                if (isLinked && sourceUrl) {
                    // Load directly from URL
                    const loadingTask = pdfjsLib.getDocument({ url: sourceUrl });
                    doc = await loadingTask.promise;
                } else if (blob) {
                    // Load from blob (stored PDF)
                    const arrayBuffer = await blob.arrayBuffer();
                    const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) });
                    doc = await loadingTask.promise;
                } else {
                    return;
                }

                if (isMounted) {
                    setPdfDocument(doc);
                    setTotalPages(doc.numPages);
                }
            } catch (err) {
                console.error('Error loading PDF document:', err);
                if (isMounted) {
                    setLoadError(err instanceof Error ? err.message : 'Failed to load PDF');
                }
            }
        };

        loadPdf();

        return () => {
            isMounted = false;
        };
    }, [blob, sourceUrl, isLinked, setTotalPages]);

    const pages = useMemo(() => {
        return Array.from({ length: totalPages }, (_, i) => i + 1);
    }, [totalPages]);

    // Preload page dimensions when PDF document loads
    usePdfPageDimensions({ pdfDocument, enabled: !!pdfDocument });

    // Scroll listener for toolbar navigation
    useEffect(() => {
        const el = document.getElementById(`pdf-page-${currentPage}`);
        if (el) {
            const rect = el.getBoundingClientRect();
            // Optional: if it's already visible or close, do not scroll (avoids interrupting manual scroll)
            if (rect.top >= -rect.height && rect.bottom <= window.innerHeight + rect.height) {
                return;
            }
            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, [currentPage]);

    if (isLoadingMetadata || isLoadingContent) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-muted/20">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-muted-foreground">Loading document...</p>
            </div>
        );
    }

    if (error || loadError || !pdfMetadata) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-muted/20 border-l border-t border-r -m-4">
                <div className="bg-destructive/10 text-destructive p-6 rounded-xl text-center max-w-md">
                    <h2 className="text-xl font-bold mb-2">Failed to load PDF</h2>
                    <p className="mb-4">
                        {loadError || (error as Error)?.message || 'Document not found'}
                    </p>
                    {isLinked && pdfMetadata?.source_url && (
                        <p className="text-sm mb-4 text-muted-foreground">
                            The PDF might be blocked by CORS. Try opening it directly:
                        </p>
                    )}
                    <div className="flex gap-2 justify-center">
                        {isLinked && pdfMetadata?.source_url && (
                            <Button
                                onClick={() => window.open(pdfMetadata.source_url!, '_blank')}
                                variant="outline"
                            >
                                <ExternalLink className="mr-2 h-4 w-4" />
                                Open in new tab
                            </Button>
                        )}
                        <Button onClick={() => navigate('/library')} variant="outline">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back to Library
                        </Button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen overflow-hidden bg-muted/30">
            <div className="flex items-center px-4 h-14 bg-background border-b shrink-0 gap-4">
                <Button variant="ghost" size="sm" onClick={() => navigate('/library')}>
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Library
                </Button>
                <div className="flex-1 truncate font-medium">
                    {pdfMetadata.title || pdfMetadata.filename}
                </div>
            </div>

            <div className="flex flex-1 overflow-hidden">
                <AnnotationSidebar />

                <div className="flex flex-col flex-1 overflow-hidden">
                    <ViewerToolbar />

                    <div className="flex-1 overflow-auto relative block p-4 md:p-8 custom-scrollbar bg-neutral-100 dark:bg-neutral-900 border-x border-b">
                        {pdfDocument && totalPages > 0 ? (
                            <div className="flex flex-col w-full max-w-5xl mx-auto transition-all">
                                {pages.map((pageNum) => (
                                    <VirtualPdfPage
                                        key={pageNum}
                                        pdfDocument={pdfDocument}
                                        pageNumber={pageNum}
                                        pdfId={id!}
                                    />
                                ))}
                            </div>
                        ) : (
                            <div className="flex items-center justify-center h-full">
                                <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
                            </div>
                        )}
                    </div>
                </div>

                <CitationPanel />
                <ChatPanel pdfId={id!} />
            </div>
        </div>
    );
}
