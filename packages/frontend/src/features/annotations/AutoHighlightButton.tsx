import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useAutoHighlightQuota } from '@/api/autoHighlight';
import { CategorySelectionDialog } from './CategorySelectionDialog';
import { ApiKeyDialog } from './ApiKeyDialog';

interface AutoHighlightButtonProps {
    pdfId: string;
}

export const AutoHighlightButton = ({ pdfId }: AutoHighlightButtonProps) => {
    const [showCategoryDialog, setShowCategoryDialog] = useState(false);
    const [showApiKeyDialog, setShowApiKeyDialog] = useState(false);
    const { data: quota } = useAutoHighlightQuota();

    const canAnalyze = quota?.has_own_key || (quota?.free_uses_remaining ?? 0) > 0;

    return (
        <div className="px-4 py-3 border-b border-border">
            <Button
                className="w-full bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white"
                onClick={() => canAnalyze ? setShowCategoryDialog(true) : setShowApiKeyDialog(true)}
            >
                <span className="mr-1.5">✦</span>
                Auto-Highlight Paper
            </Button>

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
            />

            <ApiKeyDialog
                open={showApiKeyDialog}
                onOpenChange={setShowApiKeyDialog}
            />
        </div>
    );
};
