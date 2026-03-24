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

interface DeleteConversationDialogProps {
    open: boolean;
    conversationTitle: string;
    isLoading?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

export const DeleteConversationDialog = ({
    open,
    conversationTitle,
    isLoading,
    onConfirm,
    onCancel,
}: DeleteConversationDialogProps) => (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen && !isLoading) onCancel(); }}>
        <DialogContent>
            <DialogHeader>
                <DialogTitle>Delete conversation?</DialogTitle>
                <DialogDescription>
                    <strong>&ldquo;{conversationTitle}&rdquo;</strong> and all its messages will be
                    permanently deleted. This action cannot be undone.
                </DialogDescription>
            </DialogHeader>
            <DialogFooter>
                <Button variant="ghost" onClick={onCancel} disabled={isLoading}>Cancel</Button>
                <Button variant="destructive" onClick={onConfirm} disabled={isLoading}>
                    {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    {isLoading ? 'Deleting…' : 'Delete'}
                </Button>
            </DialogFooter>
        </DialogContent>
    </Dialog>
);
