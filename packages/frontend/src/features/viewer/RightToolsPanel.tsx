import { BookOpen, MessageSquare, Download, RotateCw, Square, Maximize, Minimize, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useCitationStore } from '@/stores/citationStore';
import { useChatStore } from '@/stores/chatStore';
import { useAnnotationStore } from '@/stores/annotationStore';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetchBlob, ApiError } from '@/api/client';
import { downloadBlob } from '@/lib/download-utils';
import { toast } from 'sonner';

export const RightToolsPanel = () => {
    const { pdfId } = useParams<{ pdfId: string }>();
    const { isCitationPanelOpen, toggleCitationPanel, setCitationPanelOpen } = useCitationStore();
    const { isChatPanelOpen, toggleChatPanel, setChatPanelOpen } = useChatStore();
    const isDrawingRect = useAnnotationStore(s => s.isDrawingRect);
    const setIsDrawingRect = useAnnotationStore(s => s.setIsDrawingRect);
    const zoom = usePdfViewerStore(s => s.zoom);
    const setZoom = usePdfViewerStore(s => s.setZoom);
    const setRotation = usePdfViewerStore(s => s.setRotation);

    const [isExporting, setIsExporting] = useState(false);

    const handleToggleChat = () => {
        toggleChatPanel();
        if (!isChatPanelOpen) {
            setCitationPanelOpen(false);
        }
    };

    const handleToggleCitation = () => {
        toggleCitationPanel();
        if (!isCitationPanelOpen) {
            setChatPanelOpen(false);
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

    const handleFitWidth = () => {
        setZoom(1.0);
    };

    return (
        <div className="w-12 h-full border-l bg-background flex flex-col items-center py-3 shrink-0 gap-1 z-20">
            <Button
                variant={isCitationPanelOpen ? 'default' : 'ghost'}
                size="icon"
                className="h-9 w-9"
                onClick={handleToggleCitation}
                title="Citation"
            >
                <BookOpen className="h-4 w-4" />
            </Button>

            <Button
                variant={isChatPanelOpen ? 'default' : 'ghost'}
                size="icon"
                className="h-9 w-9"
                onClick={handleToggleChat}
                title="Chat with paper"
            >
                <MessageSquare className="h-4 w-4" />
            </Button>

            <Separator orientation="horizontal" className="w-6 my-1" />

            <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={() => setRotation((r: number) => (r + 90) % 360)}
                title="Rotate Clockwise"
            >
                <RotateCw className="h-4 w-4" />
            </Button>

            <Button
                variant={isDrawingRect ? 'default' : 'ghost'}
                size="icon"
                className="h-9 w-9"
                onClick={() => setIsDrawingRect(!isDrawingRect)}
                title="Draw Rectangle"
            >
                <Square className="h-4 w-4" />
            </Button>

            <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={handleFitWidth}
                title="Fit Width"
            >
                {zoom <= 1.05 && zoom >= 0.95 ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
            </Button>

            <Separator orientation="horizontal" className="w-6 my-1" />

            <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={handleExport}
                disabled={isExporting}
                title="Export Annotated PDF"
            >
                {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            </Button>
        </div>
    );
};
