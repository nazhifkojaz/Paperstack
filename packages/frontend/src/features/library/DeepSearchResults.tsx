import { useNavigate } from 'react-router-dom';
import { Loader2, SearchX } from 'lucide-react';
import type { SemanticSearchResult } from '@/api/chat';

interface DeepSearchResultsProps {
    results: SemanticSearchResult[];
    isLoading: boolean;
    query: string;
}

/**
 * Displays semantic search results across indexed PDFs.
 *
 * Shows three states:
 * - Loading: spinner with "Searching…" message
 * - Empty: message when no results found
 * - Results: list of PDFs with match scores and snippets
 */
export function DeepSearchResults({ results, isLoading, query }: DeepSearchResultsProps) {
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
            <p className="text-xs text-muted-foreground">
                {results.length} result{results.length !== 1 ? 's' : ''} for "{query}"
            </p>
            {results.map((r, index) => (
                <button
                    key={`${r.pdf_id}-${r.page_number}-${index}`}
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
