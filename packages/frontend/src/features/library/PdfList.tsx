import { Pdf } from '@/api/pdfs';
import { formatDistanceToNow } from 'date-fns';
import { MoreVertical, Trash, Edit, Folder, FileText, Search, Check } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { useLibraryStore } from '@/stores/libraryStore';
import { getHostname } from '@/lib/url-utils';

interface PdfListProps {
    pdfs: Pdf[];
    isLoading: boolean;
    onDelete?: (id: string) => void;
    onEdit?: (pdf: Pdf) => void;
    onManageProjects?: (pdf: Pdf) => void;
    searchQuery?: string;
}

export const PdfList = ({ pdfs, isLoading, onDelete, onEdit, onManageProjects, searchQuery }: PdfListProps) => {
    const navigate = useNavigate();
    const { isSelectionMode, selectedPdfIds, togglePdfSelection } = useLibraryStore();

    if (isLoading) {
        return (
            <div className="space-y-4">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className="flex items-center gap-4 p-4 border rounded-xl">
                        <Skeleton className="h-12 w-10 rounded" />
                        <div className="flex-1 space-y-2">
                            <Skeleton className="h-4 w-1/3 rounded" />
                            <Skeleton className="h-3 w-1/4 rounded" />
                        </div>
                        <Skeleton className="h-8 w-8 rounded-full" />
                    </div>
                ))}
            </div>
        );
    }

    if (pdfs.length === 0) {
        return (
            <EmptyState
                icon={<Search className="w-8 h-8" />}
                title="No PDFs found"
                description={searchQuery ? `We couldn't find anything matching "${searchQuery}".` : "Your library is empty. Upload a PDF to get started."}
            />
        );
    }

    return (
        <div className="flex flex-col gap-2">
            {pdfs.map((pdf) => {
                const isSelected = selectedPdfIds.has(pdf.id);

                return (
                    <div
                        key={pdf.id}
                        onClick={() => isSelectionMode ? togglePdfSelection(pdf.id) : navigate(`/viewer/${pdf.id}`)}
                        className={`group flex items-center justify-between p-3 border rounded-xl hover:bg-muted/50 cursor-pointer transition-colors ${
                            isSelectionMode ? 'cursor-pointer' : ''
                        } ${isSelected ? 'border-primary ring-1 ring-primary' : ''}`}
                    >
                        <div className="flex items-center gap-4 min-w-0">
                            {isSelectionMode && (
                                <button
                                    onClick={(e: React.MouseEvent) => {
                                        e.stopPropagation();
                                        togglePdfSelection(pdf.id);
                                    }}
                                    className={`flex-shrink-0 h-5 w-5 rounded border flex items-center justify-center transition-colors ${
                                        isSelected
                                            ? 'bg-primary border-primary text-primary-foreground'
                                            : 'border-input hover:border-primary'
                                    }`}
                                >
                                    {isSelected && <Check className="h-3.5 w-3.5" />}
                                </button>
                            )}
                            <div className="h-12 w-10 bg-primary/10 rounded flex items-center justify-center text-primary flex-shrink-0">
                                <FileText className="h-6 w-6" />
                            </div>
                            <div className="flex-col min-w-0">
                                <h4 className="font-medium text-sm truncate" title={pdf.title}>{pdf.title}</h4>
                                <p className="text-xs text-muted-foreground truncate max-w-sm" title={pdf.source_url || pdf.filename}>
                                    {pdf.source_url
                                        ? getHostname(pdf.source_url)
                                        : pdf.filename.split('/').pop() ?? pdf.filename
                                    }
                                </p>
                            </div>
                        </div>

                        <div className="flex items-center gap-6 ml-4">
                            <div className="hidden md:flex flex-col items-end text-xs text-muted-foreground whitespace-nowrap">
                                <span>{pdf.page_count ? `${pdf.page_count} pages` : 'Unknown pages'}</span>
                                <span>{formatDistanceToNow(new Date(pdf.uploaded_at), { addSuffix: true })}</span>
                            </div>

                            {!isSelectionMode && (
                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                                            <MoreVertical className="h-4 w-4" />
                                        </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end">
                                        <DropdownMenuItem onClick={(e: React.MouseEvent) => { e.stopPropagation(); onEdit?.(pdf); }}>
                                            <Edit className="mr-2 h-4 w-4" />
                                            <span>Edit Metadata</span>
                                        </DropdownMenuItem>
                                        <DropdownMenuItem onClick={(e: React.MouseEvent) => { e.stopPropagation(); onManageProjects?.(pdf); }}>
                                            <Folder className="mr-2 h-4 w-4" />
                                            <span>Manage Projects</span>
                                        </DropdownMenuItem>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem
                                            className="text-destructive focus:text-destructive"
                                            onClick={(e: React.MouseEvent) => { e.stopPropagation(); onDelete?.(pdf.id); }}
                                        >
                                            <Trash className="mr-2 h-4 w-4" />
                                            <span>Delete</span>
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

