import { useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { useAnalyzePaper } from '@/api/autoHighlight';
import { toast } from 'sonner';
import { ApiError } from '@/api/client';

const CATEGORIES = [
    { id: 'findings', label: 'Key Findings & Results', color: '#22c55e', default: true },
    { id: 'methods', label: 'Methodology', color: '#3b82f6', default: false },
    { id: 'definitions', label: 'Definitions & Key Terms', color: '#a855f7', default: false },
    { id: 'limitations', label: 'Limitations & Future Work', color: '#f97316', default: false },
    { id: 'background', label: 'Background & Prior Work', color: '#6b7280', default: false },
];

interface Props {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    pdfId: string;
}

export const CategorySelectionDialog = ({ open, onOpenChange, pdfId }: Props) => {
    const [selected, setSelected] = useState<Set<string>>(
        new Set(CATEGORIES.filter(c => c.default).map(c => c.id))
    );
    const analyzeMutation = useAnalyzePaper();

    const toggle = (id: string) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const handleAnalyze = async () => {
        if (selected.size === 0) return;

        try {
            const result = await analyzeMutation.mutateAsync({
                pdf_id: pdfId,
                categories: Array.from(selected),
            });

            toast.success(
                result.from_cache
                    ? `Loaded ${result.highlights_count} highlights from cache`
                    : `Found ${result.highlights_count} highlights`
            );
            if (result.provider_fallback) {
                toast.info('Free tier was busy — used backup model for this analysis.');
            }
            onOpenChange(false);
        } catch (error) {
            const detail = error instanceof ApiError
                ? error.message
                : error instanceof Error
                ? error.message
                : 'Analysis failed. Please try again.';
            toast.error(detail);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Auto-Highlight Settings</DialogTitle>
                    <p className="text-sm text-muted-foreground">
                        Select what to highlight in this paper
                    </p>
                </DialogHeader>

                {analyzeMutation.isPending ? (
                    <div className="flex flex-col items-center py-8 gap-3">
                        <div className="text-3xl animate-spin">✦</div>
                        <p className="text-sm font-medium">Analyzing paper...</p>
                        <p className="text-xs text-muted-foreground">This may take 10-30 seconds</p>
                    </div>
                ) : (
                    <>
                        <div className="flex flex-col gap-2">
                            {CATEGORIES.map(cat => (
                                <label
                                    key={cat.id}
                                    className={`flex items-center gap-3 p-2.5 rounded-md border cursor-pointer transition-colors ${
                                        selected.has(cat.id)
                                            ? 'border-purple-300 bg-purple-50 text-purple-900'
                                            : 'border-transparent text-foreground hover:bg-accent'
                                    }`}
                                >
                                    <Checkbox
                                        checked={selected.has(cat.id)}
                                        onCheckedChange={() => toggle(cat.id)}
                                    />
                                    <span
                                        className="w-2.5 h-2.5 rounded-full shrink-0"
                                        style={{ backgroundColor: cat.color }}
                                    />
                                    <span className="text-sm">{cat.label}</span>
                                    {cat.default && (
                                        <span className="ml-auto text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                                            default
                                        </span>
                                    )}
                                </label>
                            ))}
                        </div>

                        <DialogFooter>
                            <Button variant="outline" onClick={() => onOpenChange(false)}>
                                Cancel
                            </Button>
                            <Button
                                onClick={handleAnalyze}
                                disabled={selected.size === 0}
                                className="bg-gradient-to-r from-purple-600 to-purple-700"
                            >
                                Analyze
                            </Button>
                        </DialogFooter>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
};
