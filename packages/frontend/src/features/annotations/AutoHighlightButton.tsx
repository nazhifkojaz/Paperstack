import { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
    cancelAnalysis,
    useAutoHighlightQuota,
    useAnalysisStatus,
    useCancelAnalysis,
} from '@/api/autoHighlight';
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
    const activeCacheIdRef = useRef<string | null>(null);
    const activeStatusRef = useRef<string | null>(null);
    const notifiedRef = useRef<string | null>(null);
    const lastProgressRef = useRef<number>(0);
    const { data: quota } = useAutoHighlightQuota();
    const cancelMutation = useCancelAnalysis();
    const queryClient = useQueryClient();

    const canAnalyze = quota?.has_own_key || (quota?.free_uses_remaining ?? 0) > 0;

    // Poll for background analysis status
    const { data: statusData } = useAnalysisStatus(activeCacheId);

    // Derive "is analyzing" from state + query data (no setState in effect needed)
    const isAnalyzing =
        activeCacheId !== null &&
        (!statusData || statusData.status === 'pending' || statusData.status === 'running');
    const progressPct = statusData?.progress_pct ?? 0;

    useEffect(() => {
        activeCacheIdRef.current = activeCacheId;
        activeStatusRef.current = statusData?.status ?? null;
    }, [activeCacheId, statusData?.status]);

    useEffect(() => {
        return () => {
            const cacheId = activeCacheIdRef.current;
            const status = activeStatusRef.current;
            if (cacheId && (!status || status === 'pending' || status === 'running')) {
                void cancelAnalysis(cacheId).catch(() => undefined);
            }
        };
    }, []);

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
            toast.error(statusData.error_message ?? 'Analysis failed. Please try again.');
        } else if (statusData.status === 'cancelled') {
            notifiedRef.current = activeCacheId;
            toast('Analysis cancelled.');
        }
    }, [statusData, activeCacheId, pdfId, queryClient]);

    const handleAnalysisStarted = (cacheId: string) => {
        setActiveCacheId(cacheId);
        activeCacheIdRef.current = cacheId;
        activeStatusRef.current = 'pending';
        lastProgressRef.current = 0;
    };

    const handleCancelAnalysis = () => {
        if (!activeCacheId || cancelMutation.isPending) return;

        cancelMutation.mutate(activeCacheId, {
            onSuccess: (data) => {
                notifiedRef.current = activeCacheId;
                activeCacheIdRef.current = null;
                activeStatusRef.current = data.status;
                setActiveCacheId(null);
                queryClient.invalidateQueries({ queryKey: ['auto-highlight-cache', pdfId] });
                toast('Analysis cancelled.');
            },
            onError: () => {
                toast.error('Failed to cancel analysis.');
            },
        });
    };

    const handleButtonClick = () => {
        if (isAnalyzing) {
            handleCancelAnalysis();
        } else if (canAnalyze) {
            setShowCategoryDialog(true);
        } else {
            setShowApiKeyDialog(true);
        }
    };

    return (
        <div className="px-4 py-3 border-b border-border">
            <div className="relative">
                <Button
                    className="w-full bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white"
                    onClick={handleButtonClick}
                    disabled={cancelMutation.isPending}
                >
                    {isAnalyzing ? (
                        <>
                            <span className="mr-1.5 animate-spin">✦</span>
                            {cancelMutation.isPending
                                ? 'Cancelling...'
                                : `Cancel Analysis${progressPct > 0 ? ` ${progressPct}%` : ''}`}
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
