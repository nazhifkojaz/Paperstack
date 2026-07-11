import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useCollectionOverview, useCollections } from '@/api/collections';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';
import { ComparisonMatrix } from './ComparisonMatrix';
import { InsightsTab } from './InsightsTab';
import { CollectionTimeline } from './CollectionTimeline';
import { DuplicatesBanner } from './DuplicatesBanner';

function ComingSoon({ name }: { name: string }) {
    return (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <p className="text-lg font-medium">{name}</p>
            <p className="text-sm mt-1">Coming soon</p>
        </div>
    );
}

export function CollectionDetailPage() {
    const { collectionId } = useParams<{ collectionId: string }>();
    const { data: overview, isLoading, isError } = useCollectionOverview(collectionId ?? null);
    const { data: allCollections = [] } = useCollections();
    const collection = allCollections.find((c) => c.id === collectionId);
    const [activeTab, setActiveTab] = useState('overview');

    if (isError) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <p className="text-destructive">Failed to load collection overview.</p>
            </div>
        );
    }

    return (
        <div className="flex-1 overflow-auto bg-background/50 h-full">
            <div className="container mx-auto p-4 md:p-8 max-w-6xl">
                <div className="mb-6 flex items-center gap-4">
                    <Button variant="ghost" size="icon" asChild>
                        <Link to={`/library/collection/${collectionId}`}>
                            <ArrowLeft className="h-4 w-4" />
                        </Link>
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">
                            {collection?.name ?? 'Collection'}
                        </h1>
                        <p className="text-sm text-muted-foreground">Overview & insights</p>
                    </div>
                </div>

                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList>
                        <TabsTrigger value="overview">Overview</TabsTrigger>
                        <TabsTrigger value="compare">Compare</TabsTrigger>
                        <TabsTrigger value="timeline">Timeline</TabsTrigger>
                        <TabsTrigger value="graph">Graph</TabsTrigger>
                        <TabsTrigger value="insights">Insights</TabsTrigger>
                    </TabsList>

                    <TabsContent value="overview">
                        {isLoading ? (
                            <div className="space-y-4 mt-4">
                                <Skeleton className="h-8 w-48" />
                                <Skeleton className="h-32 w-full" />
                                <Skeleton className="h-32 w-full" />
                            </div>
                        ) : overview ? (
                            <div className="space-y-6 mt-4">
                                <DuplicatesBanner collectionId={collectionId!} />
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="rounded-lg border bg-card p-4">
                                        <p className="text-sm text-muted-foreground">Papers</p>
                                        <p className="text-3xl font-bold">{overview.paper_count}</p>
                                    </div>
                                    <div className="rounded-lg border bg-card p-4">
                                        <p className="text-sm text-muted-foreground">Indexed</p>
                                        <p className="text-3xl font-bold">{overview.indexed_count}</p>
                                    </div>
                                </div>

                                {Object.keys(overview.year_distribution).length > 0 && (
                                    <div>
                                        <h3 className="font-semibold mb-3">Year Distribution</h3>
                                        <div className="space-y-2">
                                            {Object.entries(overview.year_distribution).map(([year, count]) => {
                                                const maxCount = Math.max(
                                                    ...Object.values(overview.year_distribution),
                                                );
                                                const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                                                return (
                                                    <div key={year} className="flex items-center gap-3">
                                                        <span className="text-sm w-12 text-right text-muted-foreground">
                                                            {year}
                                                        </span>
                                                        <div className="flex-1 h-6 bg-muted rounded overflow-hidden">
                                                            <div
                                                                className="h-full bg-primary/60 rounded"
                                                                style={{ width: `${pct}%` }}
                                                            />
                                                        </div>
                                                        <span className="text-sm w-8 text-muted-foreground">
                                                            {count}
                                                        </span>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}

                                {overview.top_authors.length > 0 && (
                                    <div>
                                        <h3 className="font-semibold mb-3">Top Authors</h3>
                                        <div className="flex flex-wrap gap-2">
                                            {overview.top_authors.map((a) => (
                                                <Badge key={a.name} variant="secondary">
                                                    {a.name}
                                                    <span className="ml-1.5 text-muted-foreground">
                                                        {a.count}
                                                    </span>
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {overview.recent_papers.length > 0 && (
                                    <div>
                                        <h3 className="font-semibold mb-3">Recently Added</h3>
                                        <ul className="space-y-1">
                                            {overview.recent_papers.map((p) => (
                                                <li key={p.id} className="text-sm text-muted-foreground">
                                                    {p.title}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        ) : null}
                    </TabsContent>

                    <TabsContent value="compare">
                        <ComparisonMatrix collectionId={collectionId!} />
                    </TabsContent>

                    <TabsContent value="timeline">
                        {isLoading || !overview ? (
                            <div className="space-y-4 mt-4">
                                <Skeleton className="h-8 w-48" />
                                <Skeleton className="h-32 w-full" />
                            </div>
                        ) : (
                            <CollectionTimeline papers={overview.papers} />
                        )}
                    </TabsContent>

                    <TabsContent value="graph">
                        <ComingSoon name="Graph" />
                    </TabsContent>

                    <TabsContent value="insights">
                        <InsightsTab
                            collectionId={collectionId!}
                            onGoToCompare={() => setActiveTab('compare')}
                        />
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    );
}
