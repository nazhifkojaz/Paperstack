import { useRef, useState, useEffect } from 'react';
import { usePdfs, useDeletePdf, useBulkDeletePdfs, type Pdf } from '@/api/pdfs';
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
import { DeepSearchResults } from './DeepSearchResults';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';

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
    const bulkDeletePdfs = useBulkDeletePdfs();
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

    // Delete confirmation state
    const [deleteConfirmPdf, setDeleteConfirmPdf] = useState<Pdf | null>(null);
    const [deleteBulkConfirm, setDeleteBulkConfirm] = useState(false);

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

    // Delete handlers
    const handleDeleteClick = (id: string) => {
        const pdf = pdfs.find((p) => p.id === id);
        if (pdf) setDeleteConfirmPdf(pdf);
    };

    const handleDeleteConfirm = async () => {
        if (!deleteConfirmPdf) return;

        try {
            await toast.promise(deletePdf.mutateAsync(deleteConfirmPdf.id), {
                loading: 'Deleting PDF...',
                success: 'PDF deleted',
                error: 'Failed to delete PDF',
            });
        } catch {
            // error shown by toast
        } finally {
            setDeleteConfirmPdf(null);
        }
    };

    const handleBulkDeleteClick = () => {
        setDeleteBulkConfirm(true);
    };

    const handleBulkDeleteConfirm = async () => {
        const ids = Array.from(selectedPdfIds);
        if (ids.length === 0) return;

        try {
            await toast.promise(bulkDeletePdfs.mutateAsync(ids), {
                loading: `Deleting ${ids.length} PDF${ids.length > 1 ? 's' : ''}...`,
                success: `${ids.length} PDF${ids.length > 1 ? 's' : ''} deleted`,
                error: 'Failed to delete PDFs',
            });
            clearSelection();
            setSelectionMode(false);
        } catch {
            // error shown by toast
        } finally {
            setDeleteBulkConfirm(false);
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
                    onDelete={handleBulkDeleteClick}
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

            {/* Delete confirmation dialogs */}
            <ConfirmDialog
                open={!!deleteConfirmPdf}
                title="Delete PDF?"
                description={
                    <span>
                        <strong>&ldquo;{deleteConfirmPdf?.title}&rdquo;</strong> will be permanently deleted.
                        This action cannot be undone.
                    </span>
                }
                confirmLabel="Delete"
                variant="destructive"
                isLoading={deletePdf.isPending}
                onConfirm={handleDeleteConfirm}
                onCancel={() => setDeleteConfirmPdf(null)}
            />

            <ConfirmDialog
                open={deleteBulkConfirm}
                title={`Delete ${selectedPdfIds.size} PDF${selectedPdfIds.size > 1 ? 's' : ''}?`}
                description={
                    <span>
                        {selectedPdfIds.size} PDF{selectedPdfIds.size > 1 ? 's' : ''} will be permanently deleted.
                        This action cannot be undone.
                    </span>
                }
                confirmLabel="Delete All"
                variant="destructive"
                isLoading={bulkDeletePdfs.isPending}
                onConfirm={handleBulkDeleteConfirm}
                onCancel={() => setDeleteBulkConfirm(false)}
            />
        </div>
    );
}
