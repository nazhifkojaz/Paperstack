import { formatDistanceToNow } from 'date-fns';
import { FileText, MoreVertical, Trash, Edit, Folder, CheckSquare, Check, Link as LinkIcon } from 'lucide-react';
import { Pdf } from '@/api/pdfs';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';
import { useLibraryStore } from '@/stores/libraryStore';
import { getHostname } from '@/lib/url-utils';

interface PdfCardProps {
    pdf: Pdf;
    onDelete?: (id: string) => void;
    onEdit?: (pdf: Pdf) => void;
    onManageProjects?: (pdf: Pdf) => void;
}

export const PdfCard = ({ pdf, onDelete, onEdit, onManageProjects }: PdfCardProps) => {
    const navigate = useNavigate();
    const { isSelectionMode, selectedPdfIds, togglePdfSelection } = useLibraryStore();
    const isSelected = selectedPdfIds.has(pdf.id);

    const handleCardClick = () => {
        if (isSelectionMode) {
            togglePdfSelection(pdf.id);
        } else {
            navigate(`/viewer/${pdf.id}`);
        }
    };

    const handleCheckboxClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        togglePdfSelection(pdf.id);
    };

    return (
        <div
            className={`group relative border rounded-xl overflow-hidden bg-card text-card-foreground shadow-sm hover:shadow-md hover:border-primary/50 transition-all cursor-pointer flex flex-col ${
                isSelected ? 'border-2 border-primary' : ''
            }`}
            onClick={handleCardClick}
        >
            {/* Thumbnail Aspect Ratio Box */}
            <div className="aspect-[3/4] w-full bg-muted/30 border-b flex items-center justify-center p-6 relative">
                {/* Placeholder for actual PDF thumbnail, we use an icon for now */}
                <FileText className="h-20 w-20 text-muted-foreground/50 transition-transform group-hover:scale-110" />

                {/* Link badge for URL-based PDFs */}
                {pdf.source_url && (
                    <div className="absolute bottom-2 left-2 flex items-center gap-1 bg-background/80 backdrop-blur-sm rounded-full px-2 py-0.5 text-xs text-muted-foreground border">
                        <LinkIcon className="h-3 w-3" />
                        <span>Linked</span>
                    </div>
                )}

                {/* Selection Mode Checkbox */}
                {isSelectionMode && (
                    <div
                        className="absolute top-3 left-3 z-10"
                        onClick={handleCheckboxClick}
                    >
                        <div className={`h-6 w-6 rounded-md border-2 flex items-center justify-center transition-colors ${
                            isSelected
                                ? 'bg-primary border-primary'
                                : 'border-border bg-background/80 backdrop-blur-sm hover:border-primary/70'
                        }`}>
                            {isSelected ? (
                                <Check className="h-4 w-4 text-primary-foreground" />
                            ) : (
                                <CheckSquare className="h-4 w-4 text-muted-foreground" />
                            )}
                        </div>
                    </div>
                )}

                {/* Quick Actions overlay - hidden in selection mode */}
                {!isSelectionMode && (
                    <div
                        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => e.stopPropagation()}
                    >
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 bg-background/80 backdrop-blur-sm rounded-full shadow-sm hover:bg-background">
                                <MoreVertical className="h-4 w-4" />
                                <span className="sr-only">Open menu</span>
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => onEdit?.(pdf)}>
                                <Edit className="mr-2 h-4 w-4" />
                                <span>Edit Metadata</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => onManageProjects?.(pdf)}>
                                <Folder className="mr-2 h-4 w-4" />
                                <span>Manage Projects</span>
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                className="text-destructive focus:text-destructive"
                                onClick={() => onDelete?.(pdf.id)}
                            >
                                <Trash className="mr-2 h-4 w-4" />
                                <span>Delete</span>
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                )}
            </div>

            {/* Info Section */}
            <div className="p-4 flex-1 flex flex-col">
                <h3 className="font-semibold text-sm line-clamp-2 mb-1" title={pdf.title}>
                    {pdf.title}
                </h3>
                <p className="text-xs text-muted-foreground mb-3 truncate" title={pdf.source_url || pdf.filename}>
                    {pdf.source_url
                        ? getHostname(pdf.source_url)
                        : pdf.filename.split('/').pop() ?? pdf.filename
                    }
                </p>

                <div className="mt-auto flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>{pdf.page_count ? `${pdf.page_count} pages` : 'Unknown pages'}</span>
                    <span>{formatDistanceToNow(new Date(pdf.uploaded_at), { addSuffix: true })}</span>
                </div>
            </div>
        </div>
    );
};
