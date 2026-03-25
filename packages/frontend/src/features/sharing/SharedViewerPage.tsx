import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { pdfjsLib } from '@/lib/pdfjs';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { useSharedAnnotations } from '@/api/sharing';
import { Loader2, AlertCircle, Share2 } from 'lucide-react';
import { API_URL } from '@/lib/config';

export function SharedViewerPage() {
    const { token } = useParams<{ token: string }>();
    const { data, isLoading, isError } = useSharedAnnotations(token ?? '');
    const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);

    useEffect(() => {
        if (!data?.pdf_id) return;
        let isMounted = true;

        const load = async () => {
            try {
                const res = await fetch(`${API_URL}/shared/pdf/${token}`);
                if (!res.ok) return;
                const arrayBuffer = await res.arrayBuffer();
                const doc = await pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) }).promise;
                if (isMounted) setPdfDocument(doc);
            } catch (e) {
                console.error('Failed to load shared PDF:', e);
            }
        };

        load();
        return () => { isMounted = false; };
    }, [data?.pdf_id]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-screen bg-background">
                <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
            </div>
        );
    }

    if (isError || !data) {
        return (
            <div className="flex flex-col items-center justify-center h-screen gap-4 bg-background">
                <AlertCircle className="h-12 w-12 text-destructive" />
                <h2 className="text-xl font-semibold">Share not found</h2>
                <p className="text-sm text-muted-foreground text-center max-w-xs">
                    This share link is invalid or has been revoked.
                </p>
            </div>
        );
    }

    const { annotation_set, shared_by_login, shared_by_avatar, pdf_title } = data;

    return (
        <div className="flex flex-col h-screen overflow-hidden bg-muted/30">
            <div className="flex items-center gap-3 px-4 h-14 bg-background border-b shrink-0">
                <Share2 className="h-5 w-5 text-primary shrink-0" />
                <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{pdf_title}</p>
                    <p className="text-xs text-muted-foreground truncate">
                        <strong>{annotation_set.name}</strong> — shared by{' '}
                        {shared_by_avatar && (
                            <img src={shared_by_avatar} alt={shared_by_login} className="inline h-4 w-4 rounded-full mx-1 align-middle" />
                        )}
                        <strong>{shared_by_login}</strong>
                        <span className="ml-2 capitalize text-primary">({data.permission})</span>
                    </p>
                </div>
            </div>

            <div className="flex-1 overflow-auto p-4 md:p-8 bg-neutral-100 dark:bg-neutral-900">
                {pdfDocument ? (
                    <SharedPdfViewer pdfDocument={pdfDocument} annotations={annotation_set.annotations} setColor={annotation_set.color} />
                ) : (
                    <div className="flex items-center justify-center h-full">
                        <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
                    </div>
                )}
            </div>
        </div>
    );
}

interface AnnotationRect { x: number; y: number; w: number; h: number; }
interface SharedAnnotation { id: string; page_number: number; type: string; rects: AnnotationRect[]; color?: string | null; }

function SharedPdfViewer({ pdfDocument, annotations, setColor }: { pdfDocument: PDFDocumentProxy; annotations: SharedAnnotation[]; setColor: string }) {
    return (
        <div className="flex flex-col w-full max-w-5xl mx-auto gap-4">
            {Array.from({ length: pdfDocument.numPages }, (_, i) => i + 1).map((pageNum) => (
                <SharedPdfPage key={pageNum} pdfDocument={pdfDocument} pageNumber={pageNum} annotations={annotations.filter((a) => a.page_number === pageNum)} setColor={setColor} />
            ))}
        </div>
    );
}

function SharedPdfPage({ pdfDocument, pageNumber, annotations, setColor }: { pdfDocument: PDFDocumentProxy; pageNumber: number; annotations: SharedAnnotation[]; setColor: string }) {
    const [canvasRef, setCanvasRef] = useState<HTMLCanvasElement | null>(null);
    const [dims, setDims] = useState({ width: 0, height: 0 });

    useEffect(() => {
        if (!canvasRef) return;
        const render = async () => {
            const page = await pdfDocument.getPage(pageNumber);
            const viewport = page.getViewport({ scale: 1.2 });
            const dpr = window.devicePixelRatio || 1;
            canvasRef.width = viewport.width * dpr;
            canvasRef.height = viewport.height * dpr;
            canvasRef.style.width = `${viewport.width}px`;
            canvasRef.style.height = `${viewport.height}px`;
            setDims({ width: viewport.width, height: viewport.height });
            const ctx = canvasRef.getContext('2d')!;
            ctx.scale(dpr, dpr);
            await page.render({ canvasContext: ctx, viewport, canvas: canvasRef }).promise;
        };
        render();
    }, [canvasRef, pdfDocument, pageNumber]);

    return (
        <div className="relative shadow-lg" style={{ width: dims.width, margin: '0 auto' }}>
            <canvas ref={setCanvasRef} className="block" />
            {dims.width > 0 && (
                <svg className="absolute inset-0 pointer-events-none" width={dims.width} height={dims.height}>
                    {annotations.map((ann) => ann.rects.map((rect, idx) => (
                        <rect key={`${ann.id}-${idx}`} x={rect.x * dims.width} y={rect.y * dims.height} width={rect.w * dims.width} height={rect.h * dims.height} fill={ann.color || setColor} fillOpacity={0.35} stroke={ann.color || setColor} strokeWidth={1} strokeOpacity={0.7} />
                    )))}
                </svg>
            )}
        </div>
    );
}
