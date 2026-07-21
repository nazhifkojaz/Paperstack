import { useState } from 'react';
import { Link } from 'react-router-dom';
import { TriangleAlert, ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useCollectionDuplicates, DuplicatePair } from '@/api/collectionInsights';
import { useRemovePdfFromCollection } from '@/api/collections';

export function DuplicatesBanner({
    collectionId,
}: {
    collectionId: string;
}) {
    const { data } = useCollectionDuplicates(collectionId);
    const pairs = data?.pairs ?? [];

    if (pairs.length === 0) return null;

    return (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 mb-6">
            <DuplicatesContent collectionId={collectionId} pairs={pairs} />
        </div>
    );
}

function DuplicatesContent({
    collectionId,
    pairs,
}: {
    collectionId: string;
    pairs: DuplicatePair[];
}) {
    const defaultExpanded = pairs.length <= 3;
    const [expanded, setExpanded] = useState(defaultExpanded);

    return (
        <div>
            <button
                type="button"
                className="flex items-center gap-2 font-semibold text-sm w-full text-left"
                onClick={() => setExpanded((v) => !v)}
            >
                <TriangleAlert className="h-4 w-4 text-amber-600" />
                <span>
                    Possible duplicates ({pairs.length})
                </span>
                {expanded ? (
                    <ChevronDown className="h-4 w-4 ml-auto" />
                ) : (
                    <ChevronRight className="h-4 w-4 ml-auto" />
                )}
            </button>
            {expanded && (
                <div className="mt-3 space-y-3">
                    <p className="text-sm text-muted-foreground">
                        These papers look nearly identical:
                    </p>
                    {pairs.map((pair, i) => (
                        <PairRow
                            key={i}
                            collectionId={collectionId}
                            pair={pair}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

function PairRow({
    collectionId,
    pair,
}: {
    collectionId: string;
    pair: DuplicatePair;
}) {
    const removeFromCollection = useRemovePdfFromCollection();
    const queryClient = useQueryClient();
    const pct = Math.round(pair.similarity * 100);

    const handleRemove = (pdfId: string, title: string) => {
        if (!window.confirm(`Remove "${title}" from this collection?`)) return;
        removeFromCollection.mutate(
            { pdfId, collectionId },
            {
                onSuccess: () => {
                    queryClient.invalidateQueries({
                        queryKey: ['collection-duplicates', collectionId],
                    });
                    toast.success('Removed from collection');
                },
                onError: () => toast.error('Failed to remove'),
            },
        );
    };

    return (
        <div className="rounded-md border border-amber-500/20 bg-card/50 p-3">
            <p className="text-xs font-medium text-amber-700 mb-2">
                {pct}% similar
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
                <PaperActions
                    id={pair.pdf_a.id}
                    title={pair.pdf_a.title}
                    onRemove={handleRemove}
                    disabled={removeFromCollection.isPending}
                />
                <PaperActions
                    id={pair.pdf_b.id}
                    title={pair.pdf_b.title}
                    onRemove={handleRemove}
                    disabled={removeFromCollection.isPending}
                />
            </div>
        </div>
    );
}

function PaperActions({
    id,
    title,
    onRemove,
    disabled,
}: {
    id: string;
    title: string;
    onRemove: (id: string, title: string) => void;
    disabled: boolean;
}) {
    return (
        <div className="space-y-1">
            <p className="text-sm truncate">{title}</p>
            <div className="flex gap-1">
                <Button size="sm" variant="ghost" asChild>
                    <Link to={`/viewer/${id}`}>Open</Link>
                </Button>
                <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onRemove(id, title)}
                    disabled={disabled}
                >
                    Remove from project
                </Button>
            </div>
        </div>
    );
}
