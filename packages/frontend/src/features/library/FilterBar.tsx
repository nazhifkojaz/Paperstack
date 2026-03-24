import { useLibraryStore } from '@/stores/libraryStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { LayoutGrid, List as ListIcon, SlidersHorizontal, ArrowDownAZ, Calendar, CheckSquare, X, Search } from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface FilterBarProps {
    totalCount: number;
}

export const FilterBar = ({ totalCount }: FilterBarProps) => {
    const { viewMode, setViewMode, sortOption, setSortOption, searchQuery, setSearchQuery, isSelectionMode, setSelectionMode, isDeepSearch, setDeepSearch } = useLibraryStore();

    const handleSelectModeToggle = () => {
        if (isSelectionMode) {
            setSelectionMode(false);
        } else {
            setSelectionMode(true);
        }
    };

    return (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b mb-6">
            <div className="flex items-center gap-4">
                <span className="text-sm text-muted-foreground whitespace-nowrap">
                    {totalCount} {totalCount === 1 ? 'document' : 'documents'}
                </span>
                <div className="relative w-full max-w-xs">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        type="search"
                        placeholder="Search PDFs..."
                        className="w-full appearance-none bg-background pl-8 shadow-none h-9"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
                <div className="flex items-center gap-2">
                    <Switch
                        id="deep-search"
                        checked={isDeepSearch}
                        onCheckedChange={setDeepSearch}
                    />
                    <label htmlFor="deep-search" className="text-sm text-muted-foreground cursor-pointer select-none">
                        Deep search
                    </label>
                </div>
            </div>

            <div className="flex items-center gap-2">
                {/* Select Mode Toggle */}
                <Button
                    variant={isSelectionMode ? "destructive" : "outline"}
                    size="sm"
                    className="h-8 shadow-none"
                    onClick={handleSelectModeToggle}
                >
                    {isSelectionMode ? (
                        <>
                            <X className="mr-2 h-4 w-4" />
                            Cancel
                        </>
                    ) : (
                        <>
                            <CheckSquare className="mr-2 h-4 w-4" />
                            Select Mode
                        </>
                    )}
                </Button>

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="outline" size="sm" className="h-8 shadow-none">
                            <SlidersHorizontal className="mr-2 h-4 w-4" />
                            Sort
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem
                            onClick={() => setSortOption('-uploaded_at')}
                            className={sortOption === '-uploaded_at' ? 'bg-muted' : ''}
                        >
                            <Calendar className="mr-2 h-4 w-4" />
                            <span>Newest First</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => setSortOption('uploaded_at')}
                            className={sortOption === 'uploaded_at' ? 'bg-muted' : ''}
                        >
                            <Calendar className="mr-2 h-4 w-4" />
                            <span>Oldest First</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => setSortOption('title')}
                            className={sortOption === 'title' ? 'bg-muted' : ''}
                        >
                            <ArrowDownAZ className="mr-2 h-4 w-4" />
                            <span>A-Z</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => setSortOption('-title')}
                            className={sortOption === '-title' ? 'bg-muted' : ''}
                        >
                            <ArrowDownAZ className="mr-2 h-4 w-4" />
                            <span>Z-A</span>
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <div className="flex bg-muted/50 p-0.5 rounded-lg border">
                    <Button
                        variant="ghost"
                        size="icon"
                        className={`h-7 w-7 rounded-sm ${viewMode === 'list' ? 'bg-background shadow-sm' : ''}`}
                        onClick={() => setViewMode('list')}
                        title="List View"
                    >
                        <ListIcon className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className={`h-7 w-7 rounded-sm ${viewMode === 'grid' ? 'bg-background shadow-sm' : ''}`}
                        onClick={() => setViewMode('grid')}
                        title="Grid View"
                    >
                        <LayoutGrid className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
};
