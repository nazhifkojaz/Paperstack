import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useAnnotationStore } from '@/stores/annotationStore';
import { useAnnotationSets, useCreateAnnotationSet, useDeleteAnnotationSet, AnnotationSet } from '@/api/annotations';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Plus, Share2, PanelLeftClose, Eye, EyeOff, ChevronRight, ChevronDown, Trash2
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { ShareDialog } from '../sharing/ShareDialog';
import { Skeleton } from '@/components/ui/skeleton';
import { useSharesForSet } from '@/api/sharing';
import { SetAnnotationList } from './AnnotationList';
import { AutoHighlightButton } from './AutoHighlightButton';

export const AnnotationSidebar = () => {
    const { pdfId } = useParams<{ pdfId: string }>();
    const {
        selectedSetId, setSelectedSetId,
        isAnnotationSidebarOpen, toggleAnnotationSidebar,
        sidebarGroupBy, setSidebarGroupBy,
        toggleSetVisibility, isSetVisible,
    } = useAnnotationStore();

    const { data: annotationSets, isLoading } = useAnnotationSets(pdfId || '');
    const { mutate: createSet, isPending: isCreatingSet } = useCreateAnnotationSet();
    const { mutate: deleteSet } = useDeleteAnnotationSet();

    const [newSetName, setNewSetName] = useState('');
    const [expandedSetIds, setExpandedSetIds] = useState<Set<string>>(new Set());
    const [deletingSetId, setDeletingSetId] = useState<string | null>(null);
    const [sharingSetId, setSharingSetId] = useState<string | null>(null);
    const sharingSet = annotationSets?.find((s: AnnotationSet) => s.id === sharingSetId);
    const { data: existingShares = [] } = useSharesForSet(sharingSetId ?? '');

    const toggleExpanded = (setId: string) => {
        setExpandedSetIds(prev => {
            const next = new Set(prev);
            if (next.has(setId)) {
                next.delete(setId);
            } else {
                next.add(setId);
            }
            return next;
        });
    };

    const handleCreateSet = () => {
        if (!newSetName.trim() || !pdfId) return;
        createSet({
            pdf_id: pdfId,
            name: newSetName.trim(),
            color: '#FFFF00',
        }, {
            onSuccess: (newSet) => {
                setNewSetName('');
                if (!selectedSetId) setSelectedSetId(newSet.id);
                setExpandedSetIds(prev => new Set(prev).add(newSet.id));
            }
        });
    };

    const handleDeleteSet = (setId: string) => {
        deleteSet(setId, {
            onSuccess: () => {
                setDeletingSetId(null);
                if (selectedSetId === setId) {
                    const remaining = annotationSets?.filter(s => s.id !== setId);
                    setSelectedSetId(remaining && remaining.length > 0 ? remaining[0].id : null);
                }
                setExpandedSetIds(prev => {
                    const next = new Set(prev);
                    next.delete(setId);
                    return next;
                });
            }
        });
    };

    // Auto-select first set if none selected and data loaded
    useEffect(() => {
        if (annotationSets && annotationSets.length > 0 && !selectedSetId) {
            setSelectedSetId(annotationSets[0].id);
        }
    }, [annotationSets, selectedSetId, setSelectedSetId]);

    // Auto-expand selected set
    useEffect(() => {
        if (selectedSetId) {
            setExpandedSetIds(prev => {
                if (prev.has(selectedSetId)) return prev;
                return new Set(prev).add(selectedSetId);
            });
        }
    }, [selectedSetId]);

    if (!isAnnotationSidebarOpen) return null;

    return (
        <>
            <div className="w-80 h-full border-r bg-background flex flex-col shrink-0">
                {/* Header */}
                <div className="p-4 border-b flex items-center justify-between">
                    <h2 className="font-semibold">Annotations</h2>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={toggleAnnotationSidebar}
                        title="Close sidebar"
                    >
                        <PanelLeftClose className="h-4 w-4" />
                    </Button>
                </div>

                {/* Group Toggle */}
                <div className="p-3 border-b">
                    <div className="flex p-1 bg-muted rounded-lg">
                        <Button
                            variant={sidebarGroupBy === 'page' ? 'default' : 'ghost'}
                            size="sm"
                            className="flex-1 h-7 text-xs"
                            onClick={() => setSidebarGroupBy('page')}
                        >
                            By Page
                        </Button>
                        <Button
                            variant={sidebarGroupBy === 'type' ? 'default' : 'ghost'}
                            size="sm"
                            className="flex-1 h-7 text-xs"
                            onClick={() => setSidebarGroupBy('type')}
                        >
                            By Type
                        </Button>
                    </div>
                </div>

                {/* Auto-Highlight */}
                {pdfId && <AutoHighlightButton pdfId={pdfId} />}

                {/* Create New Set */}
                <div className="px-4 pt-4 pb-3 border-b">
                    <div className="flex gap-2">
                        <Input
                            placeholder="New set..."
                            value={newSetName}
                            onChange={(e) => setNewSetName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleCreateSet()}
                            className="h-8"
                        />
                        <Button size="icon" onClick={handleCreateSet} disabled={isCreatingSet} className="h-8 w-8 shrink-0">
                            <Plus className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                {/* Annotation Sets with nested annotations */}
                <ScrollArea className="flex-1">
                    {isLoading ? (
                        <div className="p-4 flex flex-col gap-3">
                            <Skeleton className="h-10 w-full rounded-md" />
                            <Skeleton className="h-10 w-full rounded-md" />
                        </div>
                    ) : annotationSets?.length === 0 ? (
                        <div className="p-4 text-xs text-muted-foreground">
                            No sets yet. Create one to start.
                        </div>
                    ) : (
                        <div className="py-2">
                            {annotationSets?.map((set: AnnotationSet) => {
                                const isAiSet = set.source === 'auto_highlight';
                                const visible = isSetVisible(set.id);
                                const isExpanded = expandedSetIds.has(set.id);
                                const isSelected = selectedSetId === set.id;

                                return (
                                    <div key={set.id} className="mb-0.5">
                                        {/* Set Header */}
                                        <div
                                            className={`flex items-start gap-1.5 px-3 py-2 cursor-pointer transition-colors ${
                                                isSelected
                                                    ? 'bg-primary/5'
                                                    : isAiSet
                                                    ? 'bg-purple-500/5'
                                                    : ''
                                            } ${!visible ? 'opacity-40' : ''} hover:bg-muted/50`}
                                            onClick={() => {
                                                setSelectedSetId(set.id);
                                                toggleExpanded(set.id);
                                            }}
                                        >
                                            {/* Expand/Collapse chevron */}
                                            <div className="shrink-0 mt-0.5 text-muted-foreground">
                                                {isExpanded
                                                    ? <ChevronDown size={14} />
                                                    : <ChevronRight size={14} />
                                                }
                                            </div>

                                            {/* Color dot */}
                                            <div
                                                className="w-2.5 h-2.5 rounded-full shrink-0 mt-1"
                                                style={{ backgroundColor: set.color }}
                                            />

                                            {/* AI badge */}
                                            {isAiSet && <span className="text-xs shrink-0 mt-0.5 text-purple-500">✦</span>}

                                            {/* Set name - wraps instead of truncating */}
                                            <span className={`text-sm flex-1 min-w-0 break-words leading-snug ${
                                                isSelected ? 'font-semibold' : 'font-medium'
                                            }`}>
                                                {set.name}
                                            </span>

                                            {/* Action buttons */}
                                            <div className="flex items-center gap-0.5 shrink-0">
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); toggleSetVisibility(set.id); }}
                                                    className={`p-0.5 rounded hover:bg-muted ${visible ? 'text-muted-foreground' : 'text-muted-foreground/30'}`}
                                                    title={visible ? 'Hide annotations' : 'Show annotations'}
                                                >
                                                    {visible ? <Eye size={13} /> : <EyeOff size={13} />}
                                                </button>
                                                {!isAiSet && (
                                                    <button
                                                        className="p-0.5 rounded hover:bg-muted text-muted-foreground"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setSharingSetId(set.id);
                                                        }}
                                                        title="Share this set"
                                                    >
                                                        <Share2 size={13} />
                                                    </button>
                                                )}
                                                <button
                                                    className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setDeletingSetId(set.id);
                                                    }}
                                                    title="Delete this set"
                                                >
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
                                        </div>

                                        {/* Selected indicator bar */}
                                        {isSelected && (
                                            <div
                                                className="absolute left-0 top-0 bottom-0 w-0.5 rounded-r"
                                                style={{ backgroundColor: set.color }}
                                            />
                                        )}

                                        {/* Nested annotations (collapsible) */}
                                        {isExpanded && (
                                            <div className={`border-l-2 ml-[18px] ${
                                                isAiSet ? 'border-purple-500/20' : 'border-muted'
                                            }`}>
                                                <SetAnnotationList
                                                    setId={set.id}
                                                    groupBy={sidebarGroupBy}
                                                />
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </ScrollArea>
            </div>

            {sharingSetId && sharingSet && (
                <ShareDialog
                    open={true}
                    onOpenChange={(open) => {
                        if (!open) setSharingSetId(null);
                    }}
                    setId={sharingSetId}
                    setName={sharingSet.name}
                    existingShares={existingShares}
                />
            )}

            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deletingSetId} onOpenChange={(open) => { if (!open) setDeletingSetId(null); }}>
                <DialogContent className="sm:max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Delete annotation set</DialogTitle>
                        <DialogDescription>
                            This will permanently delete "{annotationSets?.find(s => s.id === deletingSetId)?.name}" and all its annotations. This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button variant="ghost" onClick={() => setDeletingSetId(null)}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={() => deletingSetId && handleDeleteSet(deletingSetId)}>
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
};
