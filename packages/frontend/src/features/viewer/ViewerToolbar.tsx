import { type ChangeEvent } from 'react';
import { useNewPdfViewerStore } from '@/features/pdf-viewer/pdfViewerStore';
import { Button } from '@/components/ui/button';
import {
    ZoomIn, ZoomOut,
    ChevronLeft, ChevronRight,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';

export const ViewerToolbar = () => {
    const visiblePage = useNewPdfViewerStore((s) => s.visiblePage);
    const totalPages = useNewPdfViewerStore((s) => s.totalPages);
    const zoom = useNewPdfViewerStore((s) => s.zoom);
    const jumpToPage = useNewPdfViewerStore((s) => s.jumpToPage);
    const setZoom = useNewPdfViewerStore((s) => s.setZoom);
    const setZoomMode = useNewPdfViewerStore((s) => s.setZoomMode);

    const handlePageChange = (e: ChangeEvent<HTMLInputElement>) => {
        const page = parseInt(e.target.value, 10);
        if (!isNaN(page) && page >= 1 && page <= totalPages) {
            jumpToPage(page);
        }
    };

    const handleZoomChange = (newZoom: number) => {
        // Mark that we're about to zoom (for scroll anchor preservation)
        // useNewPdfViewerStore.getState().setZoom snaps, but we need to signal
        // the PdfViewer to preserve anchor.  Since the store is shared, we just
        // set zoom; PdfViewer's effects handle the rest.
        setZoomMode('manual');
        setZoom(newZoom);
    };

    return (
        <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 z-30">
            <div className="pointer-events-auto flex items-center gap-1 rounded-full bg-background/90 backdrop-blur-md border shadow-lg px-2 py-1.5">
                <Button
                    variant="ghost" size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => jumpToPage(Math.max(1, visiblePage - 1))}
                    disabled={visiblePage <= 1}
                >
                    <ChevronLeft className="h-4 w-4" />
                </Button>
                <div className="flex items-center gap-1 text-sm px-1">
                    <Input
                        type="number"
                        value={visiblePage}
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
                    onClick={() => jumpToPage(Math.min(totalPages, visiblePage + 1))}
                    disabled={visiblePage >= totalPages}
                >
                    <ChevronRight className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-5 mx-0.5" />

                <Button
                    variant="ghost" size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => handleZoomChange(Math.max(0.25, zoom - 0.25))}
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
                    onClick={() => handleZoomChange(Math.min(5.0, zoom + 0.25))}
                    title="Zoom In"
                >
                    <ZoomIn className="h-4 w-4" />
                </Button>
            </div>
        </div>
    );
};
