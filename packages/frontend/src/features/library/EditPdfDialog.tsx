import { useState, useEffect } from 'react';
import { type Pdf, useUpdatePdf } from '@/api/pdfs';
import { toast } from 'sonner';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2 } from 'lucide-react';

interface EditPdfDialogProps {
    pdf: Pdf | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export const EditPdfDialog = ({ pdf, open, onOpenChange }: EditPdfDialogProps) => {
    const [title, setTitle] = useState('');
    const [doi, setDoi] = useState('');
    const [isbn, setIsbn] = useState('');
    const [sourceUrl, setSourceUrl] = useState('');

    const updatePdf = useUpdatePdf();

    useEffect(() => {
        if (open && pdf) {
            setTitle(pdf.title);
            setDoi(pdf.doi ?? '');
            setIsbn(pdf.isbn ?? '');
            setSourceUrl(pdf.source_url ?? '');
        }
    }, [open, pdf]);

    const handleSave = async () => {
        if (!pdf || !title.trim()) return;

        try {
            await toast.promise(
                updatePdf.mutateAsync({
                    id: pdf.id,
                    data: {
                        title: title.trim(),
                        doi: doi.trim() || undefined,
                        isbn: isbn.trim() || undefined,
                        source_url: pdf.source_url ? (sourceUrl.trim() || undefined) : undefined,
                    },
                }),
                {
                    loading: 'Saving changes...',
                    success: 'PDF updated',
                    error: 'Failed to update PDF',
                }
            );
            onOpenChange(false);
        } catch {
            // error shown by toast
        }
    };

    const isLinked = !!pdf?.source_url;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Edit Metadata</DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    <div className="space-y-2">
                        <Label htmlFor="edit-title">Title</Label>
                        <Input
                            id="edit-title"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="PDF title"
                        />
                    </div>

                    {isLinked && (
                        <div className="space-y-2">
                            <Label htmlFor="edit-source-url">Source URL</Label>
                            <Input
                                id="edit-source-url"
                                type="url"
                                value={sourceUrl}
                                onChange={(e) => setSourceUrl(e.target.value)}
                                placeholder="https://..."
                            />
                        </div>
                    )}

                    <div className="space-y-2">
                        <Label htmlFor="edit-doi">DOI <span className="text-muted-foreground font-normal">(optional)</span></Label>
                        <Input
                            id="edit-doi"
                            value={doi}
                            onChange={(e) => setDoi(e.target.value)}
                            placeholder="10.1000/xyz123"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="edit-isbn">ISBN <span className="text-muted-foreground font-normal">(optional)</span></Label>
                        <Input
                            id="edit-isbn"
                            value={isbn}
                            onChange={(e) => setIsbn(e.target.value)}
                            placeholder="978-3-16-148410-0"
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={!title.trim() || updatePdf.isPending}
                    >
                        {updatePdf.isPending ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Saving...
                            </>
                        ) : (
                            'Save'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
