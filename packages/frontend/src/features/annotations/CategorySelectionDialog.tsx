import { useState, useCallback } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { useAnalyzePaper } from '@/api/autoHighlight';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { toast } from 'sonner';
import { ApiError } from '@/api/client';

const CATEGORIES = [
    { id: 'findings', label: 'Key Findings & Results', color: '#22c55e', default: true },
    { id: 'methods', label: 'Methodology', color: '#3b82f6', default: false },
    { id: 'definitions', label: 'Definitions & Key Terms', color: '#a855f7', default: false },
    { id: 'limitations', label: 'Limitations & Future Work', color: '#f97316', default: false },
    { id: 'background', label: 'Background & Prior Work', color: '#6b7280', default: false },
];

const MAX_PAGES = 15;
const DEFAULT_END = 10;

function parseFreeformPages(input: string, totalPages: number): { start: number; end: number } | null {
    const nums = new Set<number>();
    for (const part of input.split(',')) {
        const trimmed = part.trim();
        const rangeMatch = trimmed.match(/^(\d+)\s*-\s*(\d+)$/);
        if (rangeMatch) {
            const lo = parseInt(rangeMatch[1], 10);
            const hi = parseInt(rangeMatch[2], 10);
            if (isNaN(lo) || isNaN(hi) || lo > hi || lo < 1) return null;
            for (let i = lo; i <= hi; i++) nums.add(i);
        } else {
            const n = parseInt(trimmed, 10);
            if (isNaN(n) || n < 1) return null;
            nums.add(n);
        }
    }
    if (nums.size === 0) return null;
    const sorted = [...nums].sort((a, b) => a - b);
    if (totalPages > 0 && sorted[sorted.length - 1] > totalPages) return null;
    return { start: sorted[0], end: sorted[sorted.length - 1] };
}

interface Props {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    pdfId: string;
}

export const CategorySelectionDialog = ({ open, onOpenChange, pdfId }: Props) => {
    const [selected, setSelected] = useState<Set<string>>(
        new Set(CATEGORIES.filter(c => c.default).map(c => c.id))
    );
    const [pageStart, setPageStart] = useState(1);
    const [pageEnd, setPageEnd] = useState(DEFAULT_END);
    const [advancedMode, setAdvancedMode] = useState(false);
    const [freeformInput, setFreeformInput] = useState('');
    const [freeformError, setFreeformError] = useState('');

    const totalPages = usePdfViewerStore(state => state.totalPages);
    const analyzeMutation = useAnalyzePaper();

    const effectiveEnd = Math.min(pageEnd, totalPages || pageEnd);
    const pageCount = effectiveEnd - pageStart + 1;

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

    const handleStartChange = (val: string) => {
        const n = parseInt(val, 10);
        if (!isNaN(n) && n >= 1) setPageStart(n);
    };

    const handleEndChange = (val: string) => {
        const n = parseInt(val, 10);
        if (!isNaN(n) && n >= 1) setPageEnd(n);
    };

    const handleFreeformChange = useCallback((val: string) => {
        setFreeformInput(val);
        setFreeformError('');
        if (!val.trim()) return;
        const parsed = parseFreeformPages(val, totalPages);
        if (!parsed) {
            setFreeformError(totalPages > 0 ? `Invalid format or pages exceed ${totalPages}` : 'Invalid format. Use: 1, 3, 5-7');
        } else {
            setPageStart(parsed.start);
            setPageEnd(parsed.end);
        }
    }, [totalPages]);

    const handleAnalyze = async () => {
        if (selected.size === 0) return;

        if (advancedMode && freeformInput.trim()) {
            const parsed = parseFreeformPages(freeformInput, totalPages);
            if (!parsed) {
                toast.error('Invalid page range format');
                return;
            }
        }

        if (pageStart > effectiveEnd) {
            toast.error('Start page must be <= end page');
            return;
        }
        if (pageCount > MAX_PAGES) {
            toast.error(`Cannot analyze more than ${MAX_PAGES} pages at once`);
            return;
        }

        try {
            const result = await analyzeMutation.mutateAsync({
                pdf_id: pdfId,
                categories: Array.from(selected),
                page_start: pageStart,
                page_end: effectiveEnd,
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
                        <div className="flex flex-col gap-3">
                            <div className="flex items-center justify-between">
                                <label className="text-sm font-medium">
                                    Pages
                                    {totalPages > 0 && (
                                        <span className="font-normal text-muted-foreground"> of {totalPages}</span>
                                    )}
                                </label>
                                <button
                                    type="button"
                                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                    onClick={() => setAdvancedMode(!advancedMode)}
                                >
                                    {advancedMode ? 'Simple' : 'Advanced'}
                                </button>
                            </div>

                            {advancedMode ? (
                                <div className="flex flex-col gap-1.5">
                                    <Input
                                        placeholder="e.g. 1, 3, 5-7"
                                        value={freeformInput}
                                        onChange={e => handleFreeformChange(e.target.value)}
                                        className="text-sm"
                                    />
                                    {freeformError && (
                                        <p className="text-xs text-destructive">{freeformError}</p>
                                    )}
                                    {!freeformError && freeformInput.trim() && (
                                        <p className="text-xs text-muted-foreground">
                                            Resolved: pages {pageStart}–{effectiveEnd}
                                        </p>
                                    )}
                                </div>
                            ) : (
                                <div className="flex items-center gap-2">
                                    <Input
                                        type="number"
                                        min={1}
                                        max={totalPages || 999}
                                        value={pageStart}
                                        onChange={e => handleStartChange(e.target.value)}
                                        className="w-20 text-sm"
                                    />
                                    <span className="text-sm text-muted-foreground">to</span>
                                    <Input
                                        type="number"
                                        min={pageStart}
                                        max={totalPages || 999}
                                        value={pageEnd}
                                        onChange={e => handleEndChange(e.target.value)}
                                        className="w-20 text-sm"
                                    />
                                    {pageCount > MAX_PAGES && (
                                        <span className="text-xs text-destructive">
                                            Max {MAX_PAGES}
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>

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
                                disabled={selected.size === 0 || pageCount > MAX_PAGES || pageStart > effectiveEnd}
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
