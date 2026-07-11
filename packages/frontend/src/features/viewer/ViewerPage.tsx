import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { pdfjsLib } from '@/lib/pdfjs';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { useNewPdfViewerStore } from '@/features/pdf-viewer/pdfViewerStore';
import { useAnnotationStore } from '@/stores/annotationStore';
import { usePdf } from '@/api/pdfs';
import { useAnnotationSets, useMultiSetAnnotations } from '@/api/annotations';
import type { Annotation, AnnotationSet } from '@/api/annotations';
import { usePdfSource } from './usePdfSource';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { useGlobalSelectionClear } from '../annotations/useGlobalSelectionClear';
import { AnnotationsContext } from '../annotations/AnnotationsContext';
import { ViewerToolbar } from './ViewerToolbar';
import { FpsCounter } from './FpsCounter';
import { IndexStatusBadge } from './IndexStatusBadge';
import { AnnotationSidebar } from '../annotations/AnnotationSidebar';
import { CitationPanel } from '../citations/CitationPanel';
import { SummaryPanel } from '../summaries/SummaryPanel';
import { ChatPanel } from '../chat/ChatPanel';
import { RightToolsPanel } from './RightToolsPanel';
import { PdfViewer } from '@/features/pdf-viewer/PdfViewer';
import { Loader2, ArrowLeft, ExternalLink, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SettingsDialog } from '@/features/settings/SettingsDialog';
import { UserNav } from '@/components/UserNav';
import { AnnotationTooltip } from '@/features/onboarding/AnnotationTooltip';

const EMPTY_SETS: AnnotationSet[] = [];
const EMPTY_ANNOTATIONS: Annotation[] = [];

export function ViewerPage() {
    const { pdfId: id } = useParams<{ pdfId: string }>();
    const navigate = useNavigate();
    const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [settingsOpen, setSettingsOpen] = useState(false);

    const jumpToPage = useNewPdfViewerStore((s) => s.jumpToPage);

    // Annotations
    const hiddenSetIds = useAnnotationStore((s) => s.hiddenSetIds);
    const { data: rawSets } = useAnnotationSets(id ?? '');
    const allSets: AnnotationSet[] = rawSets ?? EMPTY_SETS;
    const visibleSetIds = useMemo(
        () => allSets.filter((s) => !hiddenSetIds.has(s.id)).map((s) => s.id),
        [allSets, hiddenSetIds],
    );
    const { data: allAnnotations = EMPTY_ANNOTATIONS } =
        useMultiSetAnnotations(visibleSetIds);
    const annotationsByPage = useMemo(() => {
        const map = new Map<number, Annotation[]>();
        for (const ann of allAnnotations) {
            let list = map.get(ann.page_number);
            if (!list) {
                list = [];
                map.set(ann.page_number, list);
            }
            list.push(ann);
        }
        return map;
    }, [allAnnotations]);
    const annotationsCtxValue = useMemo(
        () => ({ allSets, visibleSetIds, annotationsByPage }),
        [allSets, visibleSetIds, annotationsByPage],
    );

    useKeyboardShortcuts();
    useGlobalSelectionClear();

    const showFps =
        new URLSearchParams(window.location.search).get('fps') === '1';

    const { data: pdfMetadata, isLoading: isLoadingMetadata } =
        usePdf(id!);
    const {
        blob,
        sourceUrl,
        isLoading: isLoadingContent,
        error,
        isLinked,
    } = usePdfSource(pdfMetadata);

    // Load PDF document
    useEffect(() => {
        if (isLinked && !sourceUrl) return;
        if (!isLinked && !blob) return;

        let cancelled = false;

        (async () => {
            try {
                if (cancelled) return;
                setLoadError(null);

                let doc: PDFDocumentProxy;
                if (isLinked && sourceUrl) {
                    doc = await pdfjsLib.getDocument({ url: sourceUrl })
                        .promise;
                } else if (blob) {
                    const buffer = await blob.arrayBuffer();
                    doc = await pdfjsLib.getDocument({
                        data: new Uint8Array(buffer),
                    }).promise;
                } else {
                    return;
                }

                if (!cancelled) {
                    setPdfDocument(doc);
                }
            } catch (err) {
                console.error('Error loading PDF document:', err);
                if (!cancelled) {
                    setLoadError(
                        err instanceof Error
                            ? err.message
                            : 'Failed to load PDF',
                    );
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    }, [blob, sourceUrl, isLinked]);

    if (isLoadingMetadata || isLoadingContent) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-muted/20">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-muted-foreground">Loading document…</p>
            </div>
        );
    }

    if (error || loadError || !pdfMetadata) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-muted/20 border-l border-t border-r -m-4">
                <div className="bg-destructive/10 text-destructive p-6 rounded-xl text-center max-w-md">
                    <h2 className="text-xl font-bold mb-2">
                        Failed to load PDF
                    </h2>
                    <p className="mb-4">
                        {loadError ||
                            (error as Error)?.message ||
                            'Document not found'}
                    </p>
                    {isLinked && pdfMetadata?.source_url && (
                        <p className="text-sm mb-4 text-muted-foreground">
                            The PDF might be blocked by CORS. Try opening it
                            directly:
                        </p>
                    )}
                    <div className="flex gap-2 justify-center">
                        {isLinked && pdfMetadata?.source_url && (
                            <Button
                                onClick={() =>
                                    window.open(
                                        pdfMetadata.source_url!,
                                        '_blank',
                                    )
                                }
                                variant="outline"
                            >
                                <ExternalLink className="mr-2 h-4 w-4" />
                                Open in new tab
                            </Button>
                        )}
                        <Button
                            onClick={() => navigate('/library')}
                            variant="outline"
                        >
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
            <header className="flex items-center px-4 h-14 bg-background border-b shrink-0 gap-3">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate('/library')}
                    className="gap-1.5 shrink-0"
                >
                    <ArrowLeft className="h-4 w-4" />
                    <span className="hidden sm:inline">Library</span>
                </Button>

                <div className="flex-1 flex items-center gap-3 min-w-0">
                    <span className="truncate font-medium text-sm">
                        {pdfMetadata.title || pdfMetadata.filename}
                    </span>
                    <IndexStatusBadge pdfId={id!} />
                </div>

                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={() => setSettingsOpen(true)}
                    title="Settings"
                >
                    <Settings className="h-4 w-4" />
                </Button>

                <div className="shrink-0">
                    <UserNav />
                </div>
            </header>

            <div className="flex flex-1 overflow-hidden relative">
                <AnnotationSidebar />

                {/* Center: PDF viewer (new architecture) */}
                <div className="flex flex-col flex-1 overflow-hidden relative">
                    <AnnotationsContext.Provider
                        value={annotationsCtxValue}
                    >
                        <PdfViewer
                            pdfId={id!}
                            pdfDocument={pdfDocument}
                            isLoading={isLoadingMetadata || isLoadingContent}
                            loadError={loadError}
                        />
                    </AnnotationsContext.Provider>

                    <ViewerToolbar />
                </div>

                <RightToolsPanel />
            </div>

            <CitationPanel />
            <SummaryPanel />
            <ChatPanel pdfId={id!} jumpToPage={jumpToPage} />

            <AnnotationTooltip />

            {showFps && <FpsCounter />}
            <SettingsDialog
                open={settingsOpen}
                onOpenChange={setSettingsOpen}
            />
        </div>
    );
}
