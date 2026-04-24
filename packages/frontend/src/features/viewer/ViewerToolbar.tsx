import React, { useState } from 'react';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { useCitationStore } from '@/stores/citationStore';
import { useChatStore } from '@/stores/chatStore';
import { useAnnotationStore } from '@/stores/annotationStore';
import { Button } from '@/components/ui/button';
import {
    ZoomIn, ZoomOut, RotateCw,
    ChevronLeft, ChevronRight,
    Download, BookOpen, Square, PanelLeft, PanelLeftOpen, MessageSquare
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { useParams } from 'react-router-dom';
import { apiFetchBlob, ApiError } from '@/api/client';
import { downloadBlob } from '@/lib/download-utils';
import { toast } from 'sonner';

export const ViewerToolbar = () => {
    const { pdfId } = useParams<{ pdfId: string }>();
    const [isExporting, setIsExporting] = useState(false);
    const currentPage = usePdfViewerStore(s => s.currentPage);
    const totalPages = usePdfViewerStore(s => s.totalPages);
    const zoom = usePdfViewerStore(s => s.zoom);
    const setCurrentPage = usePdfViewerStore(s => s.setCurrentPage);
    const setZoom = usePdfViewerStore(s => s.setZoom);
    const setRotation = usePdfViewerStore(s => s.setRotation);
    const { isCitationPanelOpen, toggleCitationPanel } = useCitationStore();
    const { isChatPanelOpen, toggleChatPanel } = useChatStore();
    const isDrawingRect = useAnnotationStore(s => s.isDrawingRect);
    const isAnnotationSidebarOpen = useAnnotationStore(s => s.isAnnotationSidebarOpen);
    const setIsDrawingRect = useAnnotationStore(s => s.setIsDrawingRect);
    const toggleAnnotationSidebar = useAnnotationStore(s => s.toggleAnnotationSidebar);

    const handlePageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const page = parseInt(e.target.value, 10);
        if (!isNaN(page) && page >= 1 && page <= totalPages) {
            setCurrentPage(page);
        }
    };

    const handleExport = async () => {
        if (!pdfId || isExporting) return;
        try {
            setIsExporting(true);
            const blob = await apiFetchBlob(`/pdfs/${pdfId}/export-annotated`);
            downloadBlob(blob, `annotated_${pdfId}.pdf`);
        } catch (error) {
            const msg = error instanceof ApiError ? error.message : 'Failed to export annotated PDF.';
            toast.error(msg);
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <div className="flex items-center justify-between p-2 border-b bg-background shadow-sm z-10 sticky top-0">
            {/* Page Navigation */}
            <div className="flex items-center space-x-2">
                <Button
                    variant="ghost" size="icon"
                    onClick={toggleAnnotationSidebar}
                    title={isAnnotationSidebarOpen ? "Close sidebar (Ctrl+\\)" : "Open sidebar (Ctrl+\\)"}
                >
                    {isAnnotationSidebarOpen ? <PanelLeft className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
                </Button>
                <Separator orientation="vertical" className="h-6" />
                <Button
                    variant="ghost" size="icon"
                    onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                    disabled={currentPage <= 1}
                >
                    <ChevronLeft className="h-4 w-4" />
                </Button>
                <div className="flex items-center space-x-2 text-sm">
                    <Input
                        type="number"
                        value={currentPage}
                        onChange={handlePageChange}
                        className="w-16 h-8 text-center"
                        min={1}
                        max={totalPages || 1}
                    />
                    <span className="text-muted-foreground whitespace-nowrap">
                        / {totalPages || '-'}
                    </span>
                </div>
                <Button
                    variant="ghost" size="icon"
                    onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                    disabled={currentPage >= totalPages}
                >
                    <ChevronRight className="h-4 w-4" />
                </Button>
            </div>

            <Separator orientation="vertical" className="h-6 mx-2 hidden sm:block" />

            {/* Zoom Controls */}
            <div className="flex items-center space-x-1">
                <Button
                    variant="ghost" size="icon"
                    onClick={() => setZoom(Math.max(0.25, zoom - 0.25))}
                    title="Zoom Out"
                >
                    <ZoomOut className="h-4 w-4" />
                </Button>

                <span className="text-sm font-medium w-12 text-center select-none">
                    {Math.round(zoom * 100)}%
                </span>

                <Button
                    variant="ghost" size="icon"
                    onClick={() => setZoom(Math.min(5.0, zoom + 0.25))}
                    title="Zoom In"
                >
                    <ZoomIn className="h-4 w-4" />
                </Button>
            </div>

            <Separator orientation="vertical" className="h-6 mx-2 hidden sm:block" />

            {/* Layout & Tools */}
            <div className="flex items-center space-x-1">
                <Button
                    variant="ghost" size="icon"
                    onClick={() => setRotation((currentRotation: number) => (currentRotation + 90) % 360)}
                    title="Rotate Clockwise"
                >
                    <RotateCw className="h-4 w-4" />
                </Button>
                <Button
                    variant={isDrawingRect ? 'default' : 'ghost'}
                    size="icon"
                    onClick={() => setIsDrawingRect(!isDrawingRect)}
                    title="Draw Rectangle"
                >
                    <Square className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 mx-2" />

                <Button
                    variant={isCitationPanelOpen ? 'default' : 'outline'}
                    size="sm"
                    onClick={toggleCitationPanel}
                    className="gap-2 ml-2"
                    title="Citation"
                >
                    <BookOpen className="h-4 w-4" />
                    Citation
                </Button>

                <Button
                    variant={isChatPanelOpen ? 'default' : 'outline'}
                    size="sm"
                    onClick={toggleChatPanel}
                    className="gap-2 ml-2"
                    title="Chat with paper"
                >
                    <MessageSquare className="h-4 w-4" />
                    Chat
                </Button>

                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleExport}
                    disabled={isExporting}
                    className="gap-2 ml-2"
                >
                    {isExporting ? <span className="animate-spin text-primary">○</span> : <Download className="h-4 w-4" />}
                    Export Annotated
                </Button>
            </div>
        </div>
    );
};
