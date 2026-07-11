import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useCitationStore } from '@/stores/citationStore';
import {
    useCitation,
    useAutoExtractCitation,
    useUpdateCitation,
    useLookupCitation,
    CitationUpdate,
    LookupResponse,
} from '@/api/citations';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, Sparkles, Copy, Check, Pencil, X, Search } from 'lucide-react';
import { useClipboard } from '@/hooks/useClipboard';
import { CitationHelp } from '@/features/onboarding/CitationHelp';

function parseLookupInput(input: string): { doi?: string; isbn?: string } {
    let cleaned = input.trim();
    // Strip doi.org URL prefix
    cleaned = cleaned.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '');
    // DOI: starts with "10."
    if (/^10\./.test(cleaned)) {
        return { doi: cleaned };
    }
    // ISBN: digits and X only (after stripping hyphens/spaces), 10 or 13 chars
    const compact = cleaned.replace(/[-\s]/g, '');
    if (/^[\dXx]+$/.test(compact) && (compact.length === 10 || compact.length === 13)) {
        return { isbn: cleaned };
    }
    // Default: treat as DOI
    return { doi: cleaned };
}

export const CitationPanel = () => {
    const { pdfId } = useParams<{ pdfId: string }>();
    const { isCitationPanelOpen, toggleCitationPanel } = useCitationStore();
    const { isEditing, setIsEditing } = useCitationStore();

    const { data: citation, isLoading } = useCitation(pdfId || '');
    const autoExtract = useAutoExtractCitation(pdfId || '');
    const updateCitation = useUpdateCitation(pdfId || '');
    const lookupCitation = useLookupCitation();

    const { copied, copyToClipboard } = useClipboard();
    const [editForm, setEditForm] = useState<CitationUpdate>({});
    const [showLookup, setShowLookup] = useState(false);
    const [lookupInput, setLookupInput] = useState('');
    const [lookupResult, setLookupResult] = useState<LookupResponse | null>(null);

    const handleCopyBibtex = () => {
        if (citation?.bibtex) copyToClipboard(citation.bibtex);
    };

    const handleStartEdit = () => {
        setEditForm({
            doi: citation?.doi ?? '',
            title: citation?.title ?? '',
            authors: citation?.authors ?? '',
            year: citation?.year ?? undefined,
            bibtex: citation?.bibtex ?? '',
        });
        setIsEditing(true);
    };

    const handleSaveEdit = () => {
        updateCitation.mutate(editForm, {
            onSuccess: () => setIsEditing(false),
        });
    };

    const handleLookup = () => {
        const req = parseLookupInput(lookupInput);
        if (!req.doi && !req.isbn) return;
        setLookupResult(null);
        lookupCitation.mutate(req, {
            onSuccess: (data) => setLookupResult(data),
        });
    };

    const handleApplyLookup = () => {
        if (!lookupResult) return;
        updateCitation.mutate(
            {
                doi: lookupResult.doi ?? undefined,
                title: lookupResult.title ?? undefined,
                authors: lookupResult.authors ?? undefined,
                year: lookupResult.year ?? undefined,
                bibtex: lookupResult.bibtex,
                csl_json: lookupResult.csl_json ?? undefined,
                source: lookupResult.source,
            },
            {
                onSuccess: () => {
                    setLookupResult(null);
                    setLookupInput('');
                    setShowLookup(false);
                },
            },
        );
    };

    const resetLookup = () => {
        setShowLookup(false);
        setLookupResult(null);
        setLookupInput('');
    };

    const lookupError = lookupCitation.error?.message ?? null;

    if (!isCitationPanelOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex justify-end">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/20 backdrop-blur-[2px] backdrop-enter"
                onClick={toggleCitationPanel}
                aria-hidden="true"
            />
            {/* Drawer */}
            <div className="relative w-full max-w-[360px] h-full bg-background shadow-2xl drawer-enter flex flex-col border-l">
                {/* Header */}
                <div className="p-4 border-b flex items-center justify-between">
                    <h2 className="font-semibold">Citation</h2>
                    <div className="flex items-center gap-1">
                        <CitationHelp />
                        {citation && !isEditing && (
                            <Button variant="ghost" size="icon" onClick={handleStartEdit}>
                                <Pencil className="h-4 w-4" />
                            </Button>
                        )}
                        {isEditing && (
                            <Button variant="ghost" size="icon" onClick={() => setIsEditing(false)}>
                                <X className="h-4 w-4" />
                            </Button>
                        )}
                        <Button variant="ghost" size="icon" onClick={toggleCitationPanel} title="Close citation panel">
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                <ScrollArea className="flex-1">
                    <div className="p-4 flex flex-col gap-4">
                        {/* Auto-extract trigger */}
                        {!citation && !isLoading && (
                            <div className="space-y-3 py-4">
                                <p className="text-sm text-muted-foreground text-center">
                                    No citation found. Auto-extract from the PDF?
                                </p>
                                <Button
                                    onClick={() => autoExtract.mutate()}
                                    disabled={autoExtract.isPending}
                                    className="gap-2 w-full"
                                >
                                    {autoExtract.isPending ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Sparkles className="h-4 w-4" />
                                    )}
                                    Auto-extract
                                </Button>

                                <Button
                                    variant="link"
                                    size="sm"
                                    className="w-full"
                                    onClick={() => setShowLookup((v) => !v)}
                                >
                                    <Search className="h-3 w-3" />
                                    Look up by DOI / ISBN
                                </Button>

                                {showLookup && (
                                    <LookupBlock
                                        lookupInput={lookupInput}
                                        setLookupInput={setLookupInput}
                                        onLookup={handleLookup}
                                        isPending={lookupCitation.isPending}
                                        result={lookupResult}
                                        onApply={handleApplyLookup}
                                        isApplying={updateCitation.isPending}
                                        error={lookupError}
                                        onCancel={resetLookup}
                                    />
                                )}
                            </div>
                        )}

                        {isLoading && (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-primary/50" />
                            </div>
                        )}

                        {/* Read-only view */}
                        {citation && !isEditing && (
                            <>
                                <div className="space-y-1">
                                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Title</p>
                                    <p className="text-sm">{citation.title || '—'}</p>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Authors</p>
                                    <p className="text-sm">{citation.authors || '—'}</p>
                                </div>
                                <div className="flex gap-4">
                                    <div className="space-y-1 flex-1">
                                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Year</p>
                                        <p className="text-sm">{citation.year || '—'}</p>
                                    </div>
                                    <div className="space-y-1 flex-1">
                                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Source</p>
                                        <p className="text-sm capitalize">{citation.source}</p>
                                    </div>
                                </div>
                                {citation.doi && (
                                    <div className="space-y-1">
                                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">DOI</p>
                                        <a
                                            href={`https://doi.org/${citation.doi}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-sm text-primary hover:underline break-all"
                                        >
                                            {citation.doi}
                                        </a>
                                    </div>
                                )}

                                {/* BibTeX block */}
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">BibTeX</p>
                                        <Button variant="ghost" size="sm" onClick={handleCopyBibtex} className="h-6 gap-1 text-xs">
                                            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                            {copied ? 'Copied!' : 'Copy'}
                                        </Button>
                                    </div>
                                    <pre className="text-xs bg-muted rounded-md p-3 overflow-auto whitespace-pre-wrap break-all font-mono">
                                        {citation.bibtex}
                                    </pre>
                                </div>

                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => autoExtract.mutate()}
                                    disabled={autoExtract.isPending}
                                    className="gap-2 w-full"
                                >
                                    {autoExtract.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                                    Re-extract
                                </Button>

                                {['auto', 'manual'].includes(citation.source) && !citation.doi && (
                                    <>
                                        <Button
                                            variant="link"
                                            size="sm"
                                            className="w-full"
                                            onClick={() => setShowLookup((v) => !v)}
                                        >
                                            <Search className="h-3 w-3" />
                                            Look up by DOI / ISBN
                                        </Button>

                                        {showLookup && (
                                            <LookupBlock
                                                lookupInput={lookupInput}
                                                setLookupInput={setLookupInput}
                                                onLookup={handleLookup}
                                                isPending={lookupCitation.isPending}
                                                result={lookupResult}
                                                onApply={handleApplyLookup}
                                                isApplying={updateCitation.isPending}
                                                error={lookupError}
                                                onCancel={resetLookup}
                                            />
                                        )}
                                    </>
                                )}
                            </>
                        )}

                        {/* Edit form */}
                        {citation && isEditing && (
                            <div className="space-y-4">
                                <div className="space-y-1">
                                    <Label htmlFor="edit-title">Title</Label>
                                    <Input
                                        id="edit-title"
                                        value={editForm.title ?? ''}
                                        onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label htmlFor="edit-authors">Authors</Label>
                                    <Input
                                        id="edit-authors"
                                        value={editForm.authors ?? ''}
                                        onChange={(e) => setEditForm({ ...editForm, authors: e.target.value })}
                                    />
                                </div>
                                <div className="flex gap-2">
                                    <div className="space-y-1 flex-1">
                                        <Label htmlFor="edit-year">Year</Label>
                                        <Input
                                            id="edit-year"
                                            type="number"
                                            value={editForm.year ?? ''}
                                            onChange={(e) => setEditForm({ ...editForm, year: parseInt(e.target.value) || undefined })}
                                        />
                                    </div>
                                    <div className="space-y-1 flex-1">
                                        <Label htmlFor="edit-doi">DOI</Label>
                                        <Input
                                            id="edit-doi"
                                            value={editForm.doi ?? ''}
                                            onChange={(e) => setEditForm({ ...editForm, doi: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <Label htmlFor="edit-bibtex">BibTeX</Label>
                                    <Textarea
                                        id="edit-bibtex"
                                        className="font-mono text-xs h-40"
                                        value={editForm.bibtex ?? ''}
                                        onChange={(e) => setEditForm({ ...editForm, bibtex: e.target.value })}
                                    />
                                </div>

                                <div className="flex gap-2">
                                    <Button
                                        className="flex-1"
                                        onClick={handleSaveEdit}
                                        disabled={updateCitation.isPending}
                                    >
                                        {updateCitation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
                                    </Button>
                                    <Button variant="outline" onClick={() => setIsEditing(false)}>
                                        Cancel
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </ScrollArea>
            </div>
        </div>
    );
};

interface LookupBlockProps {
    lookupInput: string;
    setLookupInput: (v: string) => void;
    onLookup: () => void;
    isPending: boolean;
    result: LookupResponse | null;
    onApply: () => void;
    isApplying: boolean;
    error: string | null;
    onCancel: () => void;
}

const LookupBlock = ({
    lookupInput,
    setLookupInput,
    onLookup,
    isPending,
    result,
    onApply,
    isApplying,
    error,
    onCancel,
}: LookupBlockProps) => (
    <div className="space-y-2 text-left rounded-md border p-3 bg-muted/30">
        <Label htmlFor="lookup-input" className="text-xs text-muted-foreground">
            DOI or ISBN
        </Label>
        <div className="flex gap-2">
            <Input
                id="lookup-input"
                placeholder="10.1234/example or 9780262033848"
                value={lookupInput}
                onChange={(e) => setLookupInput(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') onLookup();
                }}
                className="text-sm"
            />
            <Button size="sm" onClick={onLookup} disabled={isPending || !lookupInput.trim()}>
                {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            </Button>
        </div>

        {error && (
            <p className="text-xs text-destructive">{error}</p>
        )}

        {result && (
            <div className="space-y-1 rounded-md border bg-background p-2">
                <p className="text-sm font-medium">{result.title || '—'}</p>
                {result.authors && (
                    <p className="text-xs text-muted-foreground">{result.authors}</p>
                )}
                <p className="text-xs text-muted-foreground">
                    {result.year || '—'}
                    {result.doi && ` · DOI: ${result.doi}`}
                </p>
                <div className="flex gap-2 pt-1">
                    <Button size="sm" className="flex-1" onClick={onApply} disabled={isApplying}>
                        {isApplying ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Apply'}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onCancel}>
                        Cancel
                    </Button>
                </div>
            </div>
        )}
    </div>
);
