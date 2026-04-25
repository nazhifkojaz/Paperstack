import { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { useAutoHighlightQuota, useAnalysisStatus } from '@/api/autoHighlight';
import { CategorySelectionDialog } from './CategorySelectionDialog';
import { ApiKeyDialog } from './ApiKeyDialog';
import { toast } from 'sonner';

interface AutoHighlightButtonProps {
    pdfId: string;
}

export const AutoHighlightButton = ({ pdfId }: AutoHighlightButtonProps) => {
    const [showCategoryDialog, setShowCategoryDialog] = useState(false);
    const [showApiKeyDialog, setShowApiKeyDialog] = useState(false);
    const [activeCacheId, setActiveCacheId] = useState<string | null>(null);
    const notifiedRef = useRef<string | null>(null);
    const lastProgressRef = useRef<number>(0);
    const { data: quota } = useAutoHighlightQuota();
    const queryClient = useQueryClient();

    const canAnalyze = quota?.has_own_key || (quota?.free_uses_remaining ?? 0) > 0;

    // Poll for background analysis status
    const { data: statusData } = useAnalysisStatus(activeCacheId);

    // Derive "is analyzing" from state + query data (no setState in effect needed)
    const isAnalyzing = activeCacheId !== null && (!statusData || statusData.status === 'pending');
    const progressPct = statusData?.progress_pct ?? 0;

    // Progressive invalidation: when progress_pct increases in thorough mode, invalidate annotations
    useEffect(() => {
        if (!statusData || !activeCacheId) return;
        if (statusData.progress_pct > lastProgressRef.current && statusData.annotation_set_id) {
            lastProgressRef.current = statusData.progress_pct;
            queryClient.invalidateQueries({ queryKey: ['annotations', statusData.annotation_set_id] });
        }
    }, [statusData, activeCacheId, queryClient]);

    // Fire toast + invalidation exactly once per cache ID on terminal status
    useEffect(() => {
        if (!statusData || !activeCacheId) return;
        if (notifiedRef.current === activeCacheId) return;

        if (statusData.status === 'complete' && statusData.annotation_set_id) {
            notifiedRef.current = activeCacheId;
            toast.success('Analysis complete — highlights added.');
            queryClient.invalidateQueries({ queryKey: ['annotation_sets', pdfId] });
            queryClient.invalidateQueries({ queryKey: ['auto-highlight-cache', pdfId] });
            queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
        } else if (statusData.status === 'failed') {
            notifiedRef.current = activeCacheId;
            toast.error('Analysis failed. Please try again.');
        }
    }, [statusData, activeCacheId, pdfId, queryClient]);

    const handleAnalysisStarted = (cacheId: string) => {
        setActiveCacheId(cacheId);
        lastProgressRef.current = 0;
    };

    return (
        <div className="px-4 py-3 border-b border-border">
            <div className="relative">
                <Button
                    className="w-full bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white"
                    onClick={() => canAnalyze ? setShowCategoryDialog(true) : setShowApiKeyDialog(true)}
                    disabled={isAnalyzing}
                >
                    {isAnalyzing ? (
                        <>
                            <span className="mr-1.5 animate-spin">✦</span>
                            Analyzing... {progressPct > 0 ? `${progressPct}%` : ''}
                        </>
                    ) : (
                        <>
                            <span className="mr-1.5">✦</span>
                            Auto-Highlight Paper
                        </>
                    )}
                </Button>
                {isAnalyzing && progressPct > 0 && (
                    <div
                        className="absolute bottom-0 left-0 h-0.5 bg-white/30 transition-all duration-500 rounded-b"
                        style={{ width: `${progressPct}%` }}
                    />
                )}
            </div>

            {quota && (
                <div className="mt-1.5 text-xs text-muted-foreground text-center">
                    {quota.has_own_key ? (
                        <span>Using your {quota.providers.join(', ')} key</span>
                    ) : quota.free_uses_remaining > 0 ? (
                        <span>
                            {quota.free_uses_remaining} free use{quota.free_uses_remaining !== 1 ? 's' : ''} remaining
                            {' · '}
                            <button
                                className="text-blue-400 hover:underline"
                                onClick={() => setShowApiKeyDialog(true)}
                            >
                                Add API key
                            </button>
                        </span>
                    ) : (
                        <button
                            className="text-blue-400 hover:underline"
                            onClick={() => setShowApiKeyDialog(true)}
                        >
                            Add API key to continue
                        </button>
                    )}
                </div>
            )}

            <CategorySelectionDialog
                open={showCategoryDialog}
                onOpenChange={setShowCategoryDialog}
                pdfId={pdfId}
                onAnalysisStarted={handleAnalysisStarted}
            />

            <ApiKeyDialog
                open={showApiKeyDialog}
                onOpenChange={setShowApiKeyDialog}
            />
        </div>
    );
};
