import { useState } from 'react';
import { Folder, Library, Plus, FolderOpen, MessageSquare } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useLibraryStore } from '@/stores/libraryStore';
import { useCollections, useCreateCollection } from '@/api/collections';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface SidebarProps {
    className?: string;
}

export const Sidebar = ({ className }: SidebarProps) => {
    const {
        selectedProjectId,
        setSelectedProjectId,
        resetFilters
    } = useLibraryStore();

    const { data: projects = [] } = useCollections();
    const createProject = useCreateCollection();

    const navigate = useNavigate();
    const [newProjectName, setNewProjectName] = useState('');
    const [createOpen, setCreateOpen] = useState(false);

    const handleCreateProject = async () => {
        const name = newProjectName.trim();
        if (!name) return;
        await createProject.mutateAsync({ name });
        setNewProjectName('');
        setCreateOpen(false);
    };

    return (
        <aside className={className}>
            <ScrollArea className="flex-1 py-4">
                <div className="px-3 pb-6 border-b mb-4">
                    <Button
                        variant={!selectedProjectId ? "secondary" : "ghost"}
                        className="w-full justify-start font-medium"
                        onClick={resetFilters}
                    >
                        <Library className="mr-2 h-4 w-4" />
                        All Documents
                    </Button>
                </div>

                <div className="px-3 mb-6">
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
                        {projects.map((project) => (
                            <div key={project.id} className="group flex items-center gap-1 pr-1">
                                <Button
                                    variant={selectedProjectId === project.id ? "secondary" : "ghost"}
                                    className={`flex-1 justify-start text-sm h-8 px-4 ${selectedProjectId === project.id ? 'font-medium' : 'font-normal text-muted-foreground hover:text-foreground'}`}
                                    onClick={() => setSelectedProjectId(project.id)}
                                >
                                    {selectedProjectId === project.id ? (
                                        <FolderOpen className="mr-2 h-4 w-4 opacity-70 shrink-0" />
                                    ) : (
                                        <Folder className="mr-2 h-4 w-4 opacity-70 shrink-0" />
                                    )}
                                    <span className="truncate">{project.name}</span>
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                    title="Chat with collection"
                                    onClick={() => navigate(`/chat/collection/${project.id}`)}
                                >
                                    <MessageSquare className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        ))}
                        {projects.length === 0 && (
                            <div className="px-4 py-2 text-xs text-muted-foreground text-center italic">
                                No projects yet
                            </div>
                        )}
                    </div>
                </div>
            </ScrollArea>
        </aside>
    );
};
