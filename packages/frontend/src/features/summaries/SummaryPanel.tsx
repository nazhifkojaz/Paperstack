import { useParams } from 'react-router-dom';
import { useSummaryStore } from '@/stores/summaryStore';
import { usePdfSummary, useGeneratePdfSummary } from '@/api/summaries';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, Sparkles, X } from 'lucide-react';

const SUMMARY_FIELD_ROWS: { label: string; key: keyof SummaryFields }[] = [
    { label: 'Problem', key: 'problem' },
    { label: 'Method', key: 'method' },
    { label: 'Dataset', key: 'dataset' },
    { label: 'Result', key: 'result' },
    { label: 'Contribution', key: 'contribution' },
];

interface SummaryFields {
    problem: string | null;
    method: string | null;
    dataset: string | null;
    result: string | null;
    contribution: string | null;
}

export const SummaryPanel = () => {
    const { pdfId } = useParams<{ pdfId: string }>();
    const { isSummaryPanelOpen, toggleSummaryPanel } = useSummaryStore();

    const { data: summary } = usePdfSummary(pdfId || '', true);
    const generateSummary = useGeneratePdfSummary();

    if (!isSummaryPanelOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex justify-end">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/20 backdrop-blur-[2px] backdrop-enter"
                onClick={toggleSummaryPanel}
                aria-hidden="true"
            />
            {/* Drawer */}
            <div className="relative w-full max-w-[360px] h-full bg-background shadow-2xl drawer-enter flex flex-col border-l">
                {/* Header */}
                <div className="p-4 border-b flex items-center justify-between">
                    <h2 className="font-semibold">AI Summary</h2>
                    <Button variant="ghost" size="icon" onClick={toggleSummaryPanel} title="Close summary panel">
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                <ScrollArea className="flex-1">
                    <div className="p-4 flex flex-col gap-4">
                        {pdfId && (
                            <>
                                {(summary?.status === 'complete' ||
                                    summary?.status === 'failed') && (
                                    <div className="flex justify-end">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-7 gap-1 text-xs"
                                            onClick={() => generateSummary.mutate(pdfId)}
                                            disabled={generateSummary.isPending}
                                        >
                                            {generateSummary.isPending && (
                                                <Loader2 className="h-3 w-3 animate-spin" />
                                            )}
                                            Regenerate
                                        </Button>
                                    </div>
                                )}

                                {summary?.status === 'complete' && (
                                    <div className="space-y-3">
                                        <p className="text-sm">{summary.tldr}</p>
                                        <div className="space-y-1.5">
                                            {SUMMARY_FIELD_ROWS.map(({ label, key }) => {
                                                const value = summary[key];
                                                if (!value) return null;
                                                return (
                                                    <div
                                                        key={key}
                                                        className="grid grid-cols-[6rem_1fr] gap-2"
                                                    >
                                                        <span className="text-xs text-muted-foreground shrink-0">
                                                            {label}
                                                        </span>
                                                        <span className="text-sm">{value}</span>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                        {summary.key_claims &&
                                            summary.key_claims.length > 0 && (
                                                <div className="space-y-1">
                                                    <span className="text-xs text-muted-foreground">
                                                        Key claims
                                                    </span>
                                                    <ul className="space-y-1">
                                                        {summary.key_claims.map((claim, i) => (
                                                            <li
                                                                key={i}
                                                                className="text-sm flex gap-1.5"
                                                            >
                                                                <span className="text-muted-foreground">
                                                                    •
                                                                </span>
                                                                <span>{claim}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                    </div>
                                )}

                                {summary?.status === 'generating' && (
                                    <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                        Summarizing… {summary.progress_pct}%
                                    </p>
                                )}

                                {summary?.status === 'failed' && (
                                    <p className="text-sm text-muted-foreground">
                                        Failed: {summary.error_message}
                                    </p>
                                )}

                                {!summary && (
                                    <div className="space-y-2">
                                        <p className="text-sm text-muted-foreground">
                                            No summary yet.
                                        </p>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="gap-1"
                                            onClick={() => generateSummary.mutate(pdfId)}
                                            disabled={generateSummary.isPending}
                                        >
                                            {generateSummary.isPending ? (
                                                <Loader2 className="h-3 w-3 animate-spin" />
                                            ) : (
                                                <Sparkles className="h-3 w-3" />
                                            )}
                                            Generate
                                        </Button>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </ScrollArea>
            </div>
        </div>
    );
};
