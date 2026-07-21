import { useState } from 'react';
import { Telescope, ExternalLink, Copy, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useCollectionRecommendations } from '@/api/collectionRecommendations';

function formatAuthors(authors: string[]): string {
    if (authors.length === 0) return '';
    if (authors.length <= 3) return authors.join(', ');
    const extra = authors.length - 3;
    return `${authors.slice(0, 3).join(', ')} +${extra}`;
}

export function DiscoverTab({ collectionId }: { collectionId: string }) {
    const [armed, setArmed] = useState(false);
    const { data, isLoading, isError, refetch } = useCollectionRecommendations(
        collectionId,
        armed,
    );

    // State 1 — empty / not yet armed (first visit).
    if (!armed) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-center mt-4">
                <Telescope className="h-10 w-10 text-muted-foreground" />
                <p className="text-lg font-medium mt-4">
                    Find papers you might be missing
                </p>
                <p className="text-sm text-muted-foreground max-w-md mt-2">
                    Scans the reference lists of the papers in this collection
                    via OpenAlex and surfaces works that several of your papers
                    cite — but that aren't in the collection yet.
                </p>
                <Button className="mt-6" onClick={() => setArmed(true)}>
                    Find suggested papers
                </Button>
                <p className="text-xs text-muted-foreground mt-3">
                    The first scan fetches reference data and can take a few
                    seconds per paper.
                </p>
            </div>
        );
    }

    // State 2 — loading (after click).
    if (isLoading) {
        return (
            <div className="mt-4 space-y-4">
                <h3 className="font-semibold">Suggested papers</h3>
                <p className="text-sm text-muted-foreground">
                    Scanning reference lists via OpenAlex — this can take a
                    while on the first run…
                </p>
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
            </div>
        );
    }

    // Error state.
    if (isError) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-center mt-4 space-y-3">
                <p className="text-sm text-muted-foreground">
                    Couldn't fetch suggestions — OpenAlex may be unavailable.
                    Try again.
                </p>
                <Button variant="outline" onClick={() => refetch()}>
                    Try again
                </Button>
            </div>
        );
    }

    const suggestions = data?.suggestions ?? [];
    const papersTotal = data?.papers_total ?? 0;
    const papersWithRefs = data?.papers_with_refs ?? 0;
    const papersWithoutDoi = data?.papers_without_doi ?? 0;

    // State 4 — armed, but zero suggestions (or nothing to scan).
    if (papersWithRefs === 0) {
        return (
            <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between">
                    <h3 className="font-semibold">Suggested papers (0)</h3>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => refetch()}
                    >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Refresh
                    </Button>
                </div>
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                    <p className="text-sm">
                        None of the papers in this collection have a DOI with
                        reference data, so there's nothing to scan.
                    </p>
                </div>
            </div>
        );
    }

    if (suggestions.length === 0) {
        return (
            <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between">
                    <h3 className="font-semibold">Suggested papers (0)</h3>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => refetch()}
                    >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Refresh
                    </Button>
                </div>
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                    <p className="text-sm">No strong suggestions yet.</p>
                    <p className="text-sm mt-1">
                        Suggestions appear when at least 2 of your papers cite
                        the same external work. Add more papers with DOIs and
                        re-run.
                    </p>
                </div>
            </div>
        );
    }

    // State 3 — results.
    return (
        <div className="mt-4 space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="font-semibold">
                    Suggested papers ({suggestions.length})
                </h3>
                <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => refetch()}
                >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Refresh
                </Button>
            </div>
            <p className="text-sm text-muted-foreground">
                Based on references from {papersWithRefs} of {papersTotal}{' '}
                papers.
            </p>
            {papersWithoutDoi > 0 && (
                <p className="text-xs text-muted-foreground">
                    {papersWithoutDoi === 1
                        ? "1 paper has no DOI and can't contribute references."
                        : `${papersWithoutDoi} papers have no DOI and can't contribute references.`}
                </p>
            )}
            <div className="space-y-3">
                {suggestions.map((s) => (
                    <div key={s.openalex_id} className="rounded-lg border bg-card p-4">
                        <div className="flex items-start justify-between gap-3">
                            <p className="font-medium truncate">
                                {s.title ?? 'Untitled'}
                            </p>
                            <Badge variant="secondary" className="shrink-0">
                                {s.cited_by_count} of {papersTotal} cite
                            </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-0.5">
                            {[formatAuthors(s.authors), s.year ? String(s.year) : '']
                                .filter(Boolean)
                                .join(' · ')}
                        </p>
                        <div className="flex flex-wrap gap-2 mt-2">
                            {s.doi && (
                                <>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="gap-1.5"
                                        asChild
                                    >
                                        <a
                                            href={`https://doi.org/${s.doi}`}
                                            target="_blank"
                                            rel="noreferrer"
                                        >
                                            <ExternalLink className="h-3.5 w-3.5" />
                                            DOI
                                        </a>
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="gap-1.5"
                                        onClick={() =>
                                            s.doi &&
                                            navigator.clipboard.writeText(s.doi)
                                        }
                                    >
                                        <Copy className="h-3.5 w-3.5" />
                                        Copy DOI
                                    </Button>
                                </>
                            )}
                            <Button
                                variant="ghost"
                                size="sm"
                                className="gap-1.5"
                                asChild
                            >
                                <a
                                    href={`https://openalex.org/${s.openalex_id}`}
                                    target="_blank"
                                    rel="noreferrer"
                                >
                                    <ExternalLink className="h-3.5 w-3.5" />
                                    OpenAlex
                                </a>
                            </Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
