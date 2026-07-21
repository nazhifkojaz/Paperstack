import { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, RefreshCw, Zap, Circle, GitBranch } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ApiError } from '@/api/client';
import {
    useCollectionInsight,
    useGenerateInsight,
    CollectionInsight,
    InsightCardItem,
    InsightKind,
    InsightTheme,
} from '@/api/collectionInsights';

function relativeTime(iso: string | null): string {
    if (!iso) return '';
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, now - then);
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
}

function isFewerThanTwoError(error: unknown): boolean {
    return error instanceof ApiError && error.status === 400;
}

function GenerateError({
    error,
    onGoToCompare,
}: {
    error: unknown;
    onGoToCompare?: () => void;
}) {
    const msg = error instanceof Error ? error.message : 'Failed to generate.';
    return (
        <div className="flex flex-col items-center gap-2 mt-2">
            <p className="text-xs text-destructive">{msg}</p>
            {isFewerThanTwoError(error) && onGoToCompare && (
                <Button variant="outline" size="sm" onClick={onGoToCompare}>
                    Go to Compare tab
                </Button>
            )}
        </div>
    );
}

function PaperChips({ papers }: { papers: { pdf_id: string; title: string }[] }) {
    if (papers.length === 0) return null;
    return (
        <div className="flex flex-wrap gap-1.5 mt-2">
            {papers.map((p) => (
                <Link key={p.pdf_id} to={`/viewer/${p.pdf_id}`}>
                    <Badge variant="secondary" className="cursor-pointer hover:bg-secondary/60">
                        {p.title}
                    </Badge>
                </Link>
            ))}
        </div>
    );
}

function InsightHeader({
    insight,
    onRegenerate,
    regeneratePending,
}: {
    insight: CollectionInsight;
    onRegenerate: () => void;
    regeneratePending: boolean;
}) {
    return (
        <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                {insight.generated_at && (
                    <span>
                        Generated {relativeTime(insight.generated_at)}
                        {insight.model ? ` · ${insight.model}` : ''}
                    </span>
                )}
                {insight.is_stale && (
                    <Badge
                        variant="outline"
                        className="border-amber-500/40 text-amber-600 bg-amber-500/10"
                    >
                        Outdated — collection changed
                    </Badge>
                )}
            </div>
            <Button
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={onRegenerate}
                disabled={regeneratePending}
            >
                {regeneratePending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                )}
                Regenerate
            </Button>
        </div>
    );
}

/**
 * Shared state machine for synthesis / gaps sections. Handles all non-complete
 * states (loading, empty, generating, failed) identically, then delegates the
 * complete-state payload rendering to a children callback.
 */
function InsightSection({
    collectionId,
    kind,
    emptyLabel,
    buttonLabel,
    onGoToCompare,
    children,
}: {
    collectionId: string;
    kind: InsightKind;
    emptyLabel: string;
    buttonLabel: string;
    onGoToCompare?: () => void;
    children: (insight: CollectionInsight) => ReactNode;
}) {
    const { data: insight, isLoading } = useCollectionInsight(collectionId, kind);
    const generate = useGenerateInsight(kind);
    const handleGenerate = () => generate.mutate(collectionId);

    if (isLoading) {
        return <Skeleton className="h-32 w-full" />;
    }

    if (!insight) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <p className="mb-3">{emptyLabel}</p>
                <Button onClick={handleGenerate} disabled={generate.isPending}>
                    {generate.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : null}
                    {buttonLabel}
                </Button>
                {generate.isError && (
                    <GenerateError
                        error={generate.error}
                        onGoToCompare={onGoToCompare}
                    />
                )}
            </div>
        );
    }

    if (insight.status === 'generating') {
        const count = insight.payload?.paper_count;
        return (
            <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                    Analyzing{count ? ` ${count}` : ''} papers…
                </p>
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-20 w-full" />
            </div>
        );
    }

    if (insight.status === 'failed') {
        return (
            <div className="space-y-2">
                <p className="text-sm text-destructive">
                    {insight.error_message || 'Generation failed.'}
                </p>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleGenerate}
                    disabled={generate.isPending}
                >
                    Retry
                </Button>
            </div>
        );
    }

    // Complete.
    return (
        <div className="space-y-4">
            <InsightHeader
                insight={insight}
                onRegenerate={handleGenerate}
                regeneratePending={generate.isPending}
            />
            {generate.isError && (
                <GenerateError
                    error={generate.error}
                    onGoToCompare={onGoToCompare}
                />
            )}
            {children(insight)}
        </div>
    );
}

function SynthesisContent({ insight }: { insight: CollectionInsight }) {
    return (
        <>
            {insight.payload?.synthesis && (
                <div className="rounded-lg border bg-card p-4">
                    <p className="text-sm whitespace-pre-wrap leading-relaxed">
                        {insight.payload.synthesis}
                    </p>
                </div>
            )}
            {insight.payload?.themes && insight.payload.themes.length > 0 && (
                <div>
                    <h4 className="font-semibold mb-2">Themes</h4>
                    <div className="grid gap-3 sm:grid-cols-2">
                        {insight.payload.themes.map((theme: InsightTheme) => (
                            <div
                                key={theme.name}
                                className="rounded-lg border bg-card p-3"
                            >
                                <p className="text-sm font-medium">{theme.name}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">
                                    {theme.description}
                                </p>
                                <PaperChips papers={theme.papers} />
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </>
    );
}

const GAP_CARD_META: {
    key: 'contradictions' | 'gaps' | 'lineages';
    label: string;
    Icon: typeof Zap;
}[] = [
    { key: 'contradictions', label: 'Contradiction', Icon: Zap },
    { key: 'gaps', label: 'Gap', Icon: Circle },
    { key: 'lineages', label: 'Lineage', Icon: GitBranch },
];

function GapsContent({ insight }: { insight: CollectionInsight }) {
    const payload = insight.payload;
    if (!payload) return null;
    return (
        <>
            {GAP_CARD_META.map(({ key, label, Icon }) => {
                const items = (payload[key] ?? []) as InsightCardItem[];
                if (items.length === 0) return null;
                return (
                    <div key={key} className="space-y-2">
                        {items.map((item, i) => (
                            <div
                                key={`${key}-${i}`}
                                className="rounded-lg border bg-card p-4"
                            >
                                <div className="flex items-center gap-2 mb-1">
                                    <Icon className="h-4 w-4 text-muted-foreground" />
                                    <Badge variant="outline">{label}</Badge>
                                    <span className="text-sm font-medium">
                                        {item.title}
                                    </span>
                                </div>
                                <p className="text-sm text-muted-foreground">
                                    {item.description}
                                </p>
                                <PaperChips papers={item.papers} />
                            </div>
                        ))}
                    </div>
                );
            })}
        </>
    );
}

export function InsightsTab({
    collectionId,
    onGoToCompare,
}: {
    collectionId: string;
    onGoToCompare?: () => void;
}) {
    return (
        <div className="mt-4 space-y-8">
            <section>
                <h3 className="font-semibold mb-3">Synthesis</h3>
                <InsightSection
                    collectionId={collectionId}
                    kind="synthesis"
                    emptyLabel="No synthesis yet."
                    buttonLabel="Generate synthesis"
                    onGoToCompare={onGoToCompare}
                >
                    {(insight) => <SynthesisContent insight={insight} />}
                </InsightSection>
            </section>
            <div className="border-t" />
            <section>
                <h3 className="font-semibold mb-3">Gaps &amp; Contradictions</h3>
                <InsightSection
                    collectionId={collectionId}
                    kind="gaps"
                    emptyLabel="No gap analysis yet."
                    buttonLabel="Find gaps & contradictions"
                    onGoToCompare={onGoToCompare}
                >
                    {(insight) => <GapsContent insight={insight} />}
                </InsightSection>
            </section>
        </div>
    );
}
