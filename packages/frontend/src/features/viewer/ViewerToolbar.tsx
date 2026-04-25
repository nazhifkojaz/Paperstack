import { type ChangeEvent } from 'react';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { Button } from '@/components/ui/button';
import {
    ZoomIn, ZoomOut,
    ChevronLeft, ChevronRight,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';

export const ViewerToolbar = () => {
    const currentPage = usePdfViewerStore(s => s.currentPage);
    const totalPages = usePdfViewerStore(s => s.totalPages);
    const zoom = usePdfViewerStore(s => s.zoom);
    const setCurrentPage = usePdfViewerStore(s => s.setCurrentPage);
    const setZoom = usePdfViewerStore(s => s.setZoom);

    const handlePageChange = (e: ChangeEvent<HTMLInputElement>) => {
        const page = parseInt(e.target.value, 10);
        if (!isNaN(page) && page >= 1 && page <= totalPages) {
            setCurrentPage(page);
        }
    };

    return (
        <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 z-30">
            <div className="pointer-events-auto flex items-center gap-1 rounded-full bg-background/90 backdrop-blur-md border shadow-lg px-2 py-1.5">
                {/* Page Navigation */}
                <Button
                    variant="ghost" size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                    disabled={currentPage <= 1}
                >
                    <ChevronLeft className="h-4 w-4" />
                </Button>
                <div className="flex items-center gap-1 text-sm px-1">
                    <Input
                        type="number"
                        value={currentPage}
                        onChange={handlePageChange}
                        className="w-12 h-7 text-center rounded-md text-sm px-1"
                        min={1}
                        max={totalPages || 1}
                    />
                    <span className="text-muted-foreground whitespace-nowrap text-xs">
                        / {totalPages || '-'}
                    </span>
                </div>
                <Button
                    variant="ghost" size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                    disabled={currentPage >= totalPages}
                >
                    <ChevronRight className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-5 mx-0.5" />

                {/* Zoom Controls */}
                <Button
                    variant="ghost" size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => setZoom(Math.max(0.25, zoom - 0.25))}
                    title="Zoom Out"
                >
                    <ZoomOut className="h-4 w-4" />
                </Button>
                <span className="text-xs font-medium w-10 text-center select-none">
                    {Math.round(zoom * 100)}%
                </span>
                <Button
                    variant="ghost" size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => setZoom(Math.min(5.0, zoom + 0.25))}
                    title="Zoom In"
                >
                    <ZoomIn className="h-4 w-4" />
                </Button>
            </div>
        </div>
    );
};
