import { HoverCard, HoverCardTrigger, HoverCardContent } from '@/components/ui/hover-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ExternalLink, FileText } from 'lucide-react';
import { useCitation } from '@/api/citations';
import type { ContextChunk } from '@/api/chat';
import type { Citation } from '@/api/citations';

interface InlineCitationLinkProps {
    href: string;
    children: React.ReactNode;
    contextChunks: ContextChunk[];
    onChunkClick?: (chunk: ContextChunk) => void;
    onChunkClickUrl?: (chunk: ContextChunk) => void;
}

function truncateAuthors(authors: string): string {
    if (authors.length <= 60) return authors;
    const parts = authors.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1) {
        return `${parts[0]} et al.`;
    }
    return authors.slice(0, 57) + '…';
}

function CitationPreviewCard({ citation, chunk }: { citation: Citation | null; chunk: ContextChunk }) {
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
                </div>
            </div>
        </div>
    );
}

export function InlineCitationLink({ href, children, contextChunks, onChunkClick, onChunkClickUrl }: InlineCitationLinkProps) {
    const citationIndices = href.startsWith('citation://') ? href.slice(11) : null;
    const indices = citationIndices
        ? citationIndices.split(',').flatMap((part) => {
            const range = part.split('-');
            if (range.length === 2) {
                const start = parseInt(range[0], 10);
                const end = parseInt(range[1], 10);
                if (!isNaN(start) && !isNaN(end)) {
                    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
                }
            }
            const num = parseInt(part, 10);
            return isNaN(num) ? [] : [num];
        })
        : [];

    const chunks = indices
        .map((idx) => contextChunks[idx - 1])
        .filter((chunk): chunk is ContextChunk => chunk !== undefined);

    const firstChunk = chunks[0];
    const { data: citation, isLoading } = useCitation(firstChunk?.pdf_id || '');

    if (!href.startsWith('citation://')) {
        return <a href={href}>{children}</a>;
    }

    if (chunks.length === 0) {
        return <span className="text-primary">{children}</span>;
    }

    const handleClick = (e: React.MouseEvent) => {
        e.preventDefault();
        if (onChunkClickUrl && firstChunk.pdf_id) {
            onChunkClickUrl(firstChunk);
        } else if (onChunkClick) {
            onChunkClick(firstChunk);
        }
    };

    const isClickable = onChunkClick || (onChunkClickUrl && firstChunk.pdf_id);

    return (
        <HoverCard openDelay={200} closeDelay={150}>
            <HoverCardTrigger asChild>
                <span
                    className={`text-primary ${isClickable ? 'cursor-pointer hover:underline' : ''}`}
                    onClick={isClickable ? handleClick : undefined}
                >
                    {children}
                </span>
            </HoverCardTrigger>
            <HoverCardContent side="top" align="center" className="p-0">
                {isLoading ? (
                    <div className="w-80 h-24 flex items-center justify-center">
                        <span className="text-xs text-muted-foreground animate-pulse">Loading...</span>
                    </div>
                ) : (
                    <CitationPreviewCard citation={citation ?? null} chunk={firstChunk} />
                )}
            </HoverCardContent>
        </HoverCard>
    );
}
