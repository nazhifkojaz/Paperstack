import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { CheckCircle2, XCircle } from 'lucide-react';
import { Pdf } from '@/api/pdfs';

interface ExportDialogProps {
    isOpen: boolean;
    hasCitationCount: number;
    missingPdfs: Pdf[];
    onConfirm: () => void;
    onCancel: () => void;
}

export const ExportDialog = ({
    isOpen,
    hasCitationCount,
    missingPdfs,
    onConfirm,
    onCancel,
}: ExportDialogProps) => {
    if (!isOpen) return null;

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && onCancel()}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Export Citations</DialogTitle>
                    <DialogDescription>
                        {missingPdfs.length === 0
                            ? 'All selected PDFs have citations ready for export.'
                            : 'Some PDFs are missing citations.'}
                    </DialogDescription>
                </DialogHeader>

                <div className="py-4 space-y-4">
                    {hasCitationCount > 0 && (
                        <div className="flex items-start gap-3 text-sm">
                            <CheckCircle2 className="h-5 w-5 text-green-600 mt-0.5 shrink-0" />
                            <div>
                                <span className="font-medium">{hasCitationCount} PDFs have citations</span>
                            </div>
                        </div>
                    )}

                    {missingPdfs.length > 0 && (
                        <div className="flex items-start gap-3 text-sm">
                            <XCircle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                            <div className="flex-1">
                                <span className="font-medium">{missingPdfs.length} PDF{missingPdfs.length > 1 ? 's are' : ' is'} missing citations:</span>
                                <ul className="mt-2 space-y-1 text-muted-foreground">
                                    {missingPdfs.map((pdf) => (
                                        <li key={pdf.id} className="truncate">
                                            • {pdf.title || pdf.filename}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                    )}

                    {missingPdfs.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                            Only PDFs with citations will be included in the export.
                        </p>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onCancel}>
                        Cancel
                    </Button>
                    <Button onClick={onConfirm}>
                        Export {hasCitationCount}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
