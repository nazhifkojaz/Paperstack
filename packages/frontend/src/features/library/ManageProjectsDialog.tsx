import { useEffect, useState } from 'react';
import { type Pdf, usePdfCollections } from '@/api/pdfs';
import { useCollections, useAddPdfToCollection, useRemovePdfFromCollection } from '@/api/collections';
import { toast } from 'sonner';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, FolderOpen } from 'lucide-react';

interface ManageProjectsDialogProps {
    pdf: Pdf | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export const ManageProjectsDialog = ({ pdf, open, onOpenChange }: ManageProjectsDialogProps) => {
    const { data: projects = [] } = useCollections();
    const { data: membership, isLoading: isLoadingMembership } = usePdfCollections(pdf?.id ?? '');
    const addToCollection = useAddPdfToCollection();
    const removeFromCollection = useRemovePdfFromCollection();
    // Mutations handle cache invalidation in their own onSuccess callbacks

    // Local checked state, initialised from server membership
    const [checked, setChecked] = useState<Set<string>>(new Set());
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => {
        setChecked(new Set()); // clear stale state immediately when PDF changes
        if (membership) {
            setChecked(new Set(membership.collection_ids));
        }
    }, [pdf?.id, membership]);

    const toggle = (id: string) => {
        setChecked((prev) => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const handleSave = async () => {
        if (!pdf || !membership) return;
        setIsSaving(true);

        const original = new Set(membership.collection_ids);
        const toAdd = [...checked].filter((id) => !original.has(id));
        const toRemove = [...original].filter((id) => !checked.has(id));

        try {
            await Promise.all([
                ...toAdd.map((collectionId) =>
                    addToCollection.mutateAsync({ pdfId: pdf.id, collectionId })
                ),
                ...toRemove.map((collectionId) =>
                    removeFromCollection.mutateAsync({ pdfId: pdf.id, collectionId })
                ),
            ]);
            // Note: mutations already handle cache invalidation in their onSuccess callbacks
            toast.success('Projects updated');
            onOpenChange(false);
        } catch {
            toast.error('Failed to update projects');
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-sm">
                <DialogHeader>
                    <DialogTitle>Manage Projects</DialogTitle>
                </DialogHeader>

                <div className="py-2">
                    {isLoadingMembership ? (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                    ) : projects.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-6">
                            No projects yet. Create one from the sidebar.
                        </p>
                    ) : (
                        <div className="space-y-2 max-h-64 overflow-y-auto">
                            {projects.map((project) => (
                                <label
                                    key={project.id}
                                    className="flex items-center gap-3 px-1 py-1.5 rounded-md cursor-pointer hover:bg-muted/50 text-sm"
                                >
                                    <Checkbox
                                        checked={checked.has(project.id)}
                                        onCheckedChange={() => toggle(project.id)}
                                    />
                                    <FolderOpen className="h-4 w-4 text-muted-foreground shrink-0" />
                                    <span className="truncate">{project.name}</span>
                                </label>
                            ))}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={isLoadingMembership || isSaving || projects.length === 0}
                    >
                        {isSaving ? (
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
