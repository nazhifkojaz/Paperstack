import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ExternalLink, FileText, ChevronRight } from 'lucide-react';
import type { ContextChunk } from '@/api/chat';
import type { Citation } from '@/api/citations';

interface CitationPreviewProps {
    citation: Citation | null;
    chunk: ContextChunk;
    onNavigate?: () => void;
}

function truncateAuthors(authors: string): string {
    if (authors.length <= 60) return authors;
    const parts = authors.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1) {
        return `${parts[0]} et al.`;
    }
    return authors.slice(0, 57) + '…';
}

export function CitationPreview({ citation, chunk, onNavigate }: CitationPreviewProps) {
    const title = citation?.title || chunk.pdf_title || 'Untitled';
    const authors = citation?.authors ? truncateAuthors(citation.authors) : 'Unknown authors';
    const year = citation?.year ? String(citation.year) : null;
    const snippet = chunk.snippet || 'No preview available';
    const page = chunk.page_number;
    const doi = citation?.doi;

    return (
        <div className="w-80 max-h-64 overflow-y-auto p-3 space-y-2">
            <p className="text-sm font-semibold leading-tight line-clamp-2">
                {title}
            </p>

            <p className="text-xs text-muted-foreground">
                {authors}{year ? `, ${year}` : ''}
            </p>

            <div className="border-t" />

            <p className="text-xs text-muted-foreground italic leading-relaxed line-clamp-3">
                &ldquo;{snippet}&rdquo;
            </p>

            <div className="flex items-center justify-between pt-1">
                <Badge variant="secondary" className="text-xs gap-1">
                    <FileText className="w-3 h-3" />
                    Page {page}
                </Badge>

                <div className="flex items-center gap-1">
                    {doi && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={(e) => {
                                e.stopPropagation();
                                window.open(`https://doi.org/${doi}`, '_blank');
                            }}
                            title="Open DOI"
                        >
                            <ExternalLink className="w-3 h-3" />
                        </Button>
                    )}
                    {onNavigate && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 text-xs gap-1"
                            onClick={(e) => {
                                e.stopPropagation();
                                onNavigate();
                            }}
                        >
                            Go to page
                            <ChevronRight className="w-3 h-3" />
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
}
