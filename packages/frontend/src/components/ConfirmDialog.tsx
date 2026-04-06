import { Loader2 } from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export interface ConfirmDialogProps {
    open: boolean;
    title: string;
    description: React.ReactNode;
    confirmLabel?: string;
    cancelLabel?: string;
    variant?: 'destructive' | 'default';
    isLoading?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

/**
 * Reusable confirmation dialog component.
 *
 * Supports both single-item and bulk deletion scenarios.
 * The description can be a string for simple messages or a ReactNode
 * for complex content (e.g., displaying item counts or titles).
 *
 * @example
 * ```tsx
 * // Single item deletion
 * <ConfirmDialog
 *     open={open}
 *     title="Delete PDF?"
 *     description={<>"&ldquo;{pdfTitle}&rdquo; will be permanently deleted."</>}
 *     onConfirm={handleConfirm}
 *     onCancel={handleCancel}
 * />
 *
 * // Bulk deletion
 * <ConfirmDialog
 *     open={open}
 *     title="Delete {count} PDFs?"
 *     description={<>{count} PDFs will be permanently deleted.</>}
 *     confirmLabel="Delete All"
 *     variant="destructive"
 *     onConfirm={handleConfirm}
 *     onCancel={handleCancel}
 * />
 * ```
 */
export const ConfirmDialog = ({
    open,
    title,
    description,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    variant = 'default',
    isLoading = false,
    onConfirm,
    onCancel,
}: ConfirmDialogProps) => (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen && !isLoading) onCancel(); }}>
        <DialogContent>
            <DialogHeader>
                <DialogTitle>{title}</DialogTitle>
                <DialogDescription>{description}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
                <Button variant="ghost" onClick={onCancel} disabled={isLoading}>
                    {cancelLabel}
                </Button>
                <Button variant={variant} onClick={onConfirm} disabled={isLoading}>
                    {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    {isLoading ? 'Processing…' : confirmLabel}
                </Button>
            </DialogFooter>
        </DialogContent>
    </Dialog>
);
