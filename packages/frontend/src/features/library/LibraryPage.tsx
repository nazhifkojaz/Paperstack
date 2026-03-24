import { useRef, useState, useEffect } from 'react';
import { usePdfs, useDeletePdf, type Pdf } from '@/api/pdfs';
import { useLibraryStore } from '@/stores/libraryStore';
import { useSemanticSearch, type SemanticSearchResult } from '@/api/chat';
import { useValidateCitations, useBulkExportCitations } from '@/api/citations';
import { AddPdfModal } from './AddPdfModal';
import { EditPdfDialog } from './EditPdfDialog';
import { ManageProjectsDialog } from './ManageProjectsDialog';
import { FilterBar } from './FilterBar';
import { PdfGrid } from './PdfGrid';
import { PdfList } from './PdfList';
import { FloatingActionBar } from './FloatingActionBar';
import { ExportDialog } from './ExportDialog';
import { Button } from '@/components/ui/button';
import { Plus, Loader2, SearchX } from 'lucide-react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

export function LibraryPage() {
    const {
        viewMode,
        selectedProjectId,
        searchQuery,
        sortOption,
        isSelectionMode,
        selectedPdfIds,
        clearSelection,
        setSelectionMode,
        isDeepSearch,
    } = useLibraryStore();

    const semanticSearch = useSemanticSearch();

    // Debounced semantic search
    useEffect(() => {
        if (!isDeepSearch || !searchQuery.trim()) return;
        const timer = setTimeout(() => {
            semanticSearch.mutate({
                query: searchQuery,
                collection_id: selectedProjectId ?? undefined,
                limit: 20,
            });
        }, 500);
        return () => clearTimeout(timer);
    }, [searchQuery, isDeepSearch, selectedProjectId]); // eslint-disable-line react-hooks/exhaustive-deps

    const { data: pdfs = [], isLoading, isError, error } = usePdfs({
        collection_id: selectedProjectId,
        q: searchQuery || undefined,
        sort: sortOption
    });

    const deletePdf = useDeletePdf();
    const validateCitations = useValidateCitations();
    const bulkExportCitations = useBulkExportCitations();

    const prevFilters = useRef({
        selectedProjectId,
        searchQuery,
        sortOption
    });

    // Modal / dialog state
    const [addPdfOpen, setAddPdfOpen] = useState(false);
    const [editPdf, setEditPdf] = useState<Pdf | null>(null);
    const [manageProjectsPdf, setManageProjectsPdf] = useState<Pdf | null>(null);

    // Citation export state
    const [showExportDialog, setShowExportDialog] = useState(false);
    const [validationResult, setValidationResult] = useState<{
        hasCitationCount: number;
        missingPdfs: Pdf[];
    } | null>(null);

    // Clear selection when filters change
    useEffect(() => {
        const filters = { selectedProjectId, searchQuery, sortOption };
        const filtersChanged =
            filters.selectedProjectId !== prevFilters.current.selectedProjectId ||
            filters.searchQuery !== prevFilters.current.searchQuery ||
            filters.sortOption !== prevFilters.current.sortOption;

        if (filtersChanged && isSelectionMode) clearSelection();
        prevFilters.current = filters;
    }, [selectedProjectId, searchQuery, sortOption, isSelectionMode, clearSelection]);

    const handleDelete = async (id: string) => {
        if (!window.confirm('Delete this PDF? This cannot be undone.')) return;
        try {
            await toast.promise(deletePdf.mutateAsync(id), {
                loading: 'Deleting PDF...',
                success: 'PDF deleted',
                error: 'Failed to delete PDF',
            });
        } catch {
            // error shown by toast
        }
    };

    // Citation export
    const selectedPdfs = pdfs.filter(pdf => selectedPdfIds.has(pdf.id));

    const handleExportClick = async () => {
        const pdfIds = Array.from(selectedPdfIds);
        if (pdfIds.length === 0) return;

        const result = await validateCitations.mutateAsync(pdfIds);
        const missingPdfs = pdfs.filter(pdf => result.missing.includes(pdf.id));
        const hasCitationCount = result.has_citation.length;

        if (missingPdfs.length === 0) {
            await bulkExportCitations.mutateAsync({ pdf_ids: pdfIds, format: 'bibtex' });
            setSelectionMode(false);
            return;
        }

        setValidationResult({ hasCitationCount, missingPdfs });
        setShowExportDialog(true);
    };

    const handleExportConfirm = async () => {
        if (!validationResult) return;
        const pdfsWithCitations = selectedPdfs
            .filter(pdf => !validationResult.missingPdfs.some(m => m.id === pdf.id))
            .map(pdf => pdf.id);

        if (pdfsWithCitations.length > 0) {
            await bulkExportCitations.mutateAsync({ pdf_ids: pdfsWithCitations, format: 'bibtex' });
        }
        setShowExportDialog(false);
        setValidationResult(null);
        setSelectionMode(false);
    };

    return (
        <div className="flex-1 overflow-auto bg-background/50 h-full">
            <div className="container mx-auto p-4 md:p-8 max-w-7xl">
                <div className="mb-8 flex items-start justify-between">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight mb-2">My Library</h1>
                        <p className="text-muted-foreground">
                            Manage, organize, and read your PDF documents.
                        </p>
                    </div>
                    <Button onClick={() => setAddPdfOpen(true)} className="gap-2">
                        <Plus className="h-4 w-4" />
                        Add PDF
                    </Button>
                </div>

                <div className="bg-background rounded-xl border shadow-sm p-4 md:p-6 mb-8 min-h-[500px]">
                    <FilterBar totalCount={pdfs.length} />

                    {isError ? (
                        <div className="flex flex-col items-center justify-center p-12 text-center text-destructive">
                            <p className="text-lg font-medium">Error loading PDFs</p>
                            <p className="text-sm mt-1">{(error as Error)?.message || 'Something went wrong.'}</p>
                        </div>
                    ) : isDeepSearch && searchQuery.trim() ? (
                        <DeepSearchResults
                            results={semanticSearch.data ?? []}
                            isLoading={semanticSearch.isPending}
                            query={searchQuery}
                        />
                    ) : (
                        <div className="mt-4">
                            {viewMode === 'grid' ? (
                                <PdfGrid
                                    pdfs={pdfs}
                                    isLoading={isLoading}
                                    searchQuery={searchQuery}
                                    onEdit={setEditPdf}
                                    onDelete={handleDelete}
                                    onManageProjects={setManageProjectsPdf}
                                />
                            ) : (
                                <PdfList
                                    pdfs={pdfs}
                                    isLoading={isLoading}
                                    searchQuery={searchQuery}
                                    onEdit={setEditPdf}
                                    onDelete={handleDelete}
                                    onManageProjects={setManageProjectsPdf}
                                />
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Dialogs */}
            <AddPdfModal open={addPdfOpen} onOpenChange={setAddPdfOpen} />

            <EditPdfDialog
                pdf={editPdf}
                open={!!editPdf}
                onOpenChange={(open) => { if (!open) setEditPdf(null); }}
            />

            <ManageProjectsDialog
                pdf={manageProjectsPdf}
                open={!!manageProjectsPdf}
                onOpenChange={(open) => { if (!open) setManageProjectsPdf(null); }}
            />

            {isSelectionMode && (
                <FloatingActionBar
                    selectedCount={selectedPdfIds.size}
                    onExport={handleExportClick}
                    onCancel={() => setSelectionMode(false)}
                />
            )}

            {validationResult && (
                <ExportDialog
                    isOpen={showExportDialog}
                    hasCitationCount={validationResult.hasCitationCount}
                    missingPdfs={validationResult.missingPdfs}
                    onConfirm={handleExportConfirm}
                    onCancel={() => {
                        setShowExportDialog(false);
                        setValidationResult(null);
                    }}
                />
            )}
        </div>
    );
}

// ── Deep Search Results ───────────────────────────────────────────────────────

function DeepSearchResults({
    results,
    isLoading,
    query,
}: {
    results: SemanticSearchResult[];
    isLoading: boolean;
    query: string;
}) {
    const navigate = useNavigate();

    if (isLoading) {
        return (
            <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span className="text-sm">Searching…</span>
            </div>
        );
    }

    if (results.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-muted-foreground">
                <SearchX className="h-8 w-8 opacity-40" />
                <p className="text-sm">No indexed PDFs match <strong>"{query}"</strong>.</p>
                <p className="text-xs">Open a PDF and send a chat message to index it first.</p>
            </div>
        );
    }

    return (
        <div className="mt-4 flex flex-col gap-3">
            <p className="text-xs text-muted-foreground">{results.length} result{results.length !== 1 ? 's' : ''} for "{query}"</p>
            {results.map((r) => (
                <button
                    key={`${r.pdf_id}-${r.page_number}`}
                    onClick={() => navigate(`/viewer/${r.pdf_id}`)}
                    className="w-full text-left rounded-lg border bg-card p-4 hover:bg-muted/50 transition-colors"
                >
                    <div className="flex items-start justify-between gap-2 mb-1">
                        <span className="font-medium text-sm line-clamp-1">{r.pdf_title}</span>
                        <span className="text-xs text-muted-foreground shrink-0">
                            {Math.round(r.score * 100)}% match · p.{r.page_number}
                        </span>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-2">{r.snippet}</p>
                </button>
            ))}
        </div>
    );
}
