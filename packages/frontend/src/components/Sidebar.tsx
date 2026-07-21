import { useState, useMemo } from 'react';
import { Folder, Library, Plus, FolderOpen, MessageSquare, MoreHorizontal, ChevronRight } from 'lucide-react';
import { matchPath, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useLibraryStore } from '@/stores/libraryStore';
import { useCollections, useCreateCollection, useUpdateCollection, useDeleteCollection, useExportCollection, useSwapCollectionPositions } from '@/api/collections';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmDialog } from '@/components/ConfirmDialog';

interface SidebarProps {
    className?: string;
}

interface TreeNode {
    id: string;
    name: string;
    parent_id: string | null;
    position: number;
    children: TreeNode[];
    depth: number;
}

function buildTree(
    items: { id: string; name: string; parent_id: string | null; position: number; }[],
): TreeNode[] {
    const byParentId = new Map<string | null, TreeNode[]>();
    for (const item of items) {
        const node: TreeNode = { ...item, children: [], depth: 0 };
        const list = byParentId.get(item.parent_id) || [];
        list.push(node);
        byParentId.set(item.parent_id, list);
    }
    const sortedByParent = new Map<string | null, TreeNode[]>();
    for (const [key, nodes] of byParentId) {
        sortedByParent.set(key, nodes.sort((a, b) => a.position - b.position));
    }

    function attach(parentId: string | null, depth: number): TreeNode[] {
        const children = sortedByParent.get(parentId) || [];
        for (const child of children) {
            child.depth = depth;
            child.children = attach(child.id, depth + 1);
        }
        return children;
    }

    return attach(null, 0);
}

function getDescendantIds(node: TreeNode): Set<string> {
    const ids = new Set<string>();
    for (const child of node.children) {
        ids.add(child.id);
        for (const id of getDescendantIds(child)) {
            ids.add(id);
        }
    }
    return ids;
}

function getSiblings(tree: TreeNode[], nodeId: string): TreeNode[] {
    for (const node of tree) {
        if (node.children.some((c) => c.id === nodeId)) {
            return node.children;
        }
        if (node.id === nodeId && node.depth === 0) {
            return tree;
        }
        const result = getSiblings(node.children, nodeId);
        if (result.length > 0) return result;
    }
    return [];
}

function findNode(tree: TreeNode[], id: string): TreeNode | null {
    for (const node of tree) {
        if (node.id === id) return node;
        const found = findNode(node.children, id);
        if (found) return found;
    }
    return null;
}

function getRoutedCollectionId(pathname: string): string | null {
    const routes = [
        '/library/collection/:collectionId/overview',
        '/library/collection/:collectionId',
        '/chat/collection/:collectionId',
    ];
    for (const route of routes) {
        const collectionId = matchPath(route, pathname)?.params.collectionId;
        if (collectionId) return collectionId;
    }
    return null;
}

export const Sidebar = ({ className }: SidebarProps) => {
    const {
        selectedProjectId,
        resetFilters
    } = useLibraryStore();

    const { data: projects = [] } = useCollections();
    const createProject = useCreateCollection();
    const updateCollection = useUpdateCollection();
    const swapCollectionPositions = useSwapCollectionPositions();
    const deleteCollection = useDeleteCollection();
    const exportCollection = useExportCollection();

    const navigate = useNavigate();
    const location = useLocation();
    const routedCollectionId = getRoutedCollectionId(location.pathname);
    const activeCollectionId = routedCollectionId ?? selectedProjectId;
    const [newProjectName, setNewProjectName] = useState('');
    const [createOpen, setCreateOpen] = useState(false);

    const [renameTarget, setRenameTarget] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState('');

    const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

    const tree = useMemo(() => buildTree(projects), [projects]);

    const handleCreateProject = async () => {
        const name = newProjectName.trim();
        if (!name) return;
        try {
            await createProject.mutateAsync({ name });
            setNewProjectName('');
            setCreateOpen(false);
        } catch {
            toast.error('Failed to create project');
        }
    };

    const handleMove = async (collectionId: string, parentId: string | null) => {
        try {
            await updateCollection.mutateAsync({ id: collectionId, parent_id: parentId });
        } catch {
            toast.error('Failed to move collection');
        }
    };

    const handleReorder = async (collectionId: string, offset: -1 | 1) => {
        const siblings = getSiblings(tree, collectionId);
        const idx = siblings.findIndex((s) => s.id === collectionId);
        const adjacentIdx = idx + offset;
        if (idx < 0 || adjacentIdx < 0 || adjacentIdx >= siblings.length) return;
        const current = siblings[idx];
        const adjacent = siblings[adjacentIdx];
        try {
            await swapCollectionPositions.mutateAsync({
                firstId: current.id,
                secondId: adjacent.id,
            });
        } catch {
            toast.error('Failed to reorder collection');
        }
    };

    const handleDelete = async () => {
        if (!deleteTarget) return;
        const collectionId = deleteTarget;
        try {
            await deleteCollection.mutateAsync(collectionId);
            if (
                routedCollectionId === collectionId
                || selectedProjectId === collectionId
            ) {
                resetFilters();
                navigate('/library', { replace: true });
            }
            setDeleteTarget(null);
        } catch {
            toast.error('Failed to delete collection');
            setDeleteTarget(null);
        }
    };

    const renderProjectNode = (node: TreeNode) => {
        const isSelected = activeCollectionId === node.id;
        const indentPx = 4 + node.depth * 16;

        const handleRenameSubmit = async () => {
            if (renameValue.trim()) {
                try {
                    await updateCollection.mutateAsync({
                        id: node.id,
                        name: renameValue.trim(),
                    });
                } catch {
                    toast.error('Failed to rename collection');
                }
            }
            setRenameTarget(null);
        };

        return (
            <div key={node.id}>
                <div className="group flex items-center gap-1 pr-1">
                    <Button
                        variant={isSelected ? "secondary" : "ghost"}
                        className={`flex-1 justify-start text-sm h-8 px-4 ${isSelected ? 'font-medium' : 'font-normal text-muted-foreground hover:text-foreground'}`}
                        style={{ paddingLeft: node.depth > 0 ? `${indentPx}px` : undefined }}
                        onClick={() => {
                            navigate(`/library/collection/${node.id}`);
                        }}
                    >
                        {isSelected ? (
                            <FolderOpen className="mr-2 h-4 w-4 opacity-70 shrink-0" />
                        ) : (
                            <Folder className="mr-2 h-4 w-4 opacity-70 shrink-0" />
                        )}
                        <span className="truncate">{node.name}</span>
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Chat with collection"
                        onClick={() => navigate(`/chat/collection/${node.id}`)}
                    >
                        <MessageSquare className="h-3.5 w-3.5" />
                    </Button>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                title="More options"
                            >
                                <MoreHorizontal className="h-3.5 w-3.5" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                            <DropdownMenuItem
                                onClick={() => navigate(`/library/collection/${node.id}/overview`)}
                            >
                                Overview
                            </DropdownMenuItem>
                            <DropdownMenuItem
                                onClick={() => exportCollection.mutate({ id: node.id, format: 'bibtex' })}
                            >
                                Export BibTeX
                            </DropdownMenuItem>
                            <DropdownMenuItem
                                onClick={() => exportCollection.mutate({ id: node.id, format: 'markdown' })}
                            >
                                Export Markdown
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                onClick={() => {
                                    setRenameTarget(node.id);
                                    setRenameValue(node.name);
                                }}
                            >
                                Rename
                            </DropdownMenuItem>
                            <DropdownMenuSub>
                                <DropdownMenuSubTrigger>
                                    Move to...
                                </DropdownMenuSubTrigger>
                                <DropdownMenuSubContent className="w-40">
                                    {(() => {
                                        const nodeInTree = findNode(tree, node.id);
                                        const descendants = nodeInTree ? getDescendantIds(nodeInTree) : new Set<string>();
                                        const validTargets = projects.filter(
                                            (p) => p.id !== node.id && !descendants.has(p.id),
                                        );

                                        return (
                                            <>
                                                {node.parent_id !== null && (
                                                    <DropdownMenuItem onClick={() => handleMove(node.id, null)}>
                                                        <ChevronRight className="h-3.5 w-3.5 opacity-0" />
                                                        Top level
                                                    </DropdownMenuItem>
                                                )}
                                                {validTargets.map((p) => (
                                                    <DropdownMenuItem
                                                        key={p.id}
                                                        onClick={() => handleMove(node.id, p.id)}
                                                    >
                                                        {p.name}
                                                    </DropdownMenuItem>
                                                ))}
                                                {validTargets.length === 0 && node.parent_id === null && (
                                                    <DropdownMenuItem disabled>No other collections</DropdownMenuItem>
                                                )}
                                            </>
                                        );
                                    })()}
                                </DropdownMenuSubContent>
                            </DropdownMenuSub>
                            <DropdownMenuItem onClick={() => handleReorder(node.id, -1)}>
                                Move up
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleReorder(node.id, 1)}>
                                Move down
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                className="text-destructive focus:text-destructive"
                                onClick={() => setDeleteTarget(node.id)}
                            >
                                Delete
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                {renameTarget === node.id && (
                    <div
                        className="flex items-center gap-1 px-2 py-1"
                        style={{ marginLeft: `${indentPx}px` }}
                    >
                        <Input
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            className="h-7 text-sm"
                            autoFocus
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    handleRenameSubmit();
                                } else if (e.key === 'Escape') {
                                    setRenameTarget(null);
                                }
                            }}
                            onBlur={handleRenameSubmit}
                        />
                    </div>
                )}
                {node.children.map(renderProjectNode)}
            </div>
        );
    };

    return (
        <aside className={className}>
            <ScrollArea className="flex-1 py-4">
                <div className="px-3 pb-6 border-b mb-4">
                    <Button
                        variant={!activeCollectionId ? "secondary" : "ghost"}
                        className="w-full justify-start font-medium"
                        onClick={() => {
                            resetFilters();
                            navigate('/library');
                        }}
                    >
                        <Library className="mr-2 h-4 w-4" />
                        All Documents
                    </Button>
                </div>

                <div className="px-3 mb-6" data-tour="sidebar-projects">
                    <div className="flex items-center justify-between mb-2 px-4">
                        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Projects
                        </h3>
                        <Popover open={createOpen} onOpenChange={setCreateOpen}>
                            <PopoverTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-5 w-5 rounded-full hover:bg-muted" title="New Project">
                                    <Plus className="h-3 w-3" />
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-56 p-3" align="end">
                                <form
                                    onSubmit={(e) => {
                                        e.preventDefault();
                                        handleCreateProject();
                                    }}
                                    className="flex flex-col gap-2"
                                >
                                    <Input
                                        placeholder="Project name"
                                        value={newProjectName}
                                        onChange={(e) => setNewProjectName(e.target.value)}
                                        autoFocus
                                        className="h-8 text-sm"
                                    />
                                    <Button
                                        type="submit"
                                        size="sm"
                                        className="h-7 text-xs"
                                        disabled={!newProjectName.trim() || createProject.isPending}
                                    >
                                        {createProject.isPending ? 'Creating...' : 'Create'}
                                    </Button>
                                </form>
                            </PopoverContent>
                        </Popover>
                    </div>
                    <div className="space-y-1">
                        {tree.map(renderProjectNode)}
                        {projects.length === 0 && (
                            <div className="px-4 py-2 text-xs text-muted-foreground text-center italic">
                                No projects yet
                            </div>
                        )}
                    </div>
                </div>
            </ScrollArea>

            <ConfirmDialog
                open={!!deleteTarget}
                title="Delete collection?"
                description={
                    <span>
                        Are you sure you want to delete this collection? The PDFs
                        themselves will <strong>not</strong> be deleted.
                    </span>
                }
                confirmLabel="Delete"
                variant="destructive"
                isLoading={deleteCollection.isPending}
                onConfirm={handleDelete}
                onCancel={() => setDeleteTarget(null)}
            />
        </aside>
    );
};
