import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useCitationStore } from '@/stores/citationStore';
import { useCitation, useAutoExtractCitation, useUpdateCitation, CitationUpdate } from '@/api/citations';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, Sparkles, Copy, Check, Pencil, X } from 'lucide-react';

export const CitationPanel = () => {
    const { pdfId } = useParams<{ pdfId: string }>();
    const { isPanelOpen } = useCitationStore();
    const { isEditing, setIsEditing } = useCitationStore();

    const { data: citation, isLoading } = useCitation(pdfId || '');
    const autoExtract = useAutoExtractCitation(pdfId || '');
    const updateCitation = useUpdateCitation(pdfId || '');

    const [copied, setCopied] = useState(false);
    const [editForm, setEditForm] = useState<CitationUpdate>({});

    const handleCopyBibtex = () => {
        if (!citation?.bibtex) return;
        navigator.clipboard.writeText(citation.bibtex);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
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

    if (!isPanelOpen) return null;

    return (
        <div className="w-80 h-full border-l bg-background flex flex-col shrink-0">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between">
                <h2 className="font-semibold">Citation</h2>
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
            </div>

            <ScrollArea className="flex-1">
                <div className="p-4 flex flex-col gap-4">
                    {/* Auto-extract trigger */}
                    {!citation && !isLoading && (
                        <div className="text-center space-y-3 py-4">
                            <p className="text-sm text-muted-foreground">
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
    );
};
