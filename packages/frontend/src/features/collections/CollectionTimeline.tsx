import { Link } from 'react-router-dom';
import { CollectionOverviewPaper } from '@/api/collections';

interface CollectionTimelineProps {
    papers: CollectionOverviewPaper[];
}

export function CollectionTimeline({ papers }: CollectionTimelineProps) {
    if (papers.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <p className="text-sm">No papers in this collection yet.</p>
            </div>
        );
    }

    // Group by year; null years collected into a final "Unknown" group.
    const byYear = new Map<number | null, CollectionOverviewPaper[]>();
    for (const p of papers) {
        const key = p.year ?? null;
        const arr = byYear.get(key);
        if (arr) {
            arr.push(p);
        } else {
            byYear.set(key, [p]);
        }
    }

    const knownYears = [...byYear.keys()].filter(
        (y): y is number => y !== null,
    ).sort((a, b) => b - a); // descending

    const unknownPapers = byYear.get(null) ?? [];

    return (
        <div className="mt-4 space-y-6">
            {knownYears.map((year) => (
                <YearGroup key={year} year={year} papers={byYear.get(year)!} />
            ))}
            {unknownPapers.length > 0 && (
                <YearGroup year={null} papers={unknownPapers} />
            )}
        </div>
    );
}

function YearGroup({
    year,
    papers,
}: {
    year: number | null;
    papers: CollectionOverviewPaper[];
}) {
    return (
        <div className="relative pl-20">
            {/* Spine */}
            <div className="absolute left-[4.5rem] top-1 bottom-0 border-l-2 border-muted" />
            {/* Year dot */}
            <div className="absolute left-[4.5rem] top-1 -translate-x-1/2">
                <div className="h-3 w-3 rounded-full bg-primary" />
            </div>
            {/* Year label */}
            <span className="absolute left-0 top-0.5 w-16 text-right font-semibold tabular-nums text-sm">
                {year ?? 'Unknown'}
            </span>
            <div className="space-y-2 pb-2">
                {papers.map((p) => (
                    <Link
                        key={p.id}
                        to={`/viewer/${p.id}`}
                        className="block rounded-lg border bg-card px-4 py-2 hover:bg-accent transition-colors"
                    >
                        <p className="text-sm font-medium truncate">
                            {p.title}
                        </p>
                        {p.first_author && (
                            <p className="text-xs text-muted-foreground">
                                {p.first_author}
                            </p>
                        )}
                    </Link>
                ))}
            </div>
        </div>
    );
}
