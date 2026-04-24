import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, Link as LinkIcon, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import { useUploadPdf, useLinkPdf, useCheckPdfUrl, PdfUrlCheckResponse } from '@/api/pdfs';
import { toast } from 'sonner';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ProjectPicker } from './ProjectPicker';

interface AddPdfModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

function formatFileSize(bytes: number | null | undefined): string {
    if (!bytes) return 'unknown size';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const AddPdfModal = ({ open, onOpenChange }: AddPdfModalProps) => {
    // Upload File tab state
    const [file, setFile] = useState<File | null>(null);
    const [uploadTitle, setUploadTitle] = useState('');
    const [uploadProjectIds, setUploadProjectIds] = useState<string[]>([]);

    // Add URL tab state
    const [url, setUrl] = useState('');
    const [urlTitle, setUrlTitle] = useState('');
    const [urlProjectIds, setUrlProjectIds] = useState<string[]>([]);

    // URL check state
    const [checkResult, setCheckResult] = useState<PdfUrlCheckResponse | null>(null);
    const [checkError, setCheckError] = useState<string | null>(null);

    const uploadMutation = useUploadPdf();
    const linkMutation = useLinkPdf();
    const checkUrlMutation = useCheckPdfUrl();

    const resetState = () => {
        setFile(null);
        setUploadTitle('');
        setUploadProjectIds([]);
        setUrl('');
        setUrlTitle('');
        setUrlProjectIds([]);
        setCheckResult(null);
        setCheckError(null);
    };

    const handleOpenChange = (nextOpen: boolean) => {
        if (!nextOpen) resetState();
        onOpenChange(nextOpen);
    };

    const onDrop = useCallback((acceptedFiles: File[]) => {
        const pdfFile = acceptedFiles[0];
        if (!pdfFile) return;
        if (pdfFile.type !== 'application/pdf') {
            toast.error(`${pdfFile.name} is not a valid PDF file`);
            return;
        }
        setFile(pdfFile);
        if (!uploadTitle) {
            setUploadTitle(pdfFile.name.replace(/\.pdf$/i, ''));
        }
    }, [uploadTitle]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: { 'application/pdf': ['.pdf'] },
        maxFiles: 1,
    });

    const handleUpload = async () => {
        if (!file || !uploadTitle.trim()) return;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', uploadTitle.trim());
        if (uploadProjectIds.length > 0) {
            formData.append('project_ids', uploadProjectIds.join(','));
        }

        try {
            await toast.promise(uploadMutation.mutateAsync(formData), {
                loading: `Uploading ${file.name}...`,
                success: `Successfully uploaded ${file.name}`,
                error: `Failed to upload ${file.name}`,
            });
            handleOpenChange(false);
        } catch {
            // error already shown by toast
        }
    };

    const handleLink = async () => {
        if (!url.trim() || !urlTitle.trim() || !checkResult?.valid) return;

        try {
            await toast.promise(linkMutation.mutateAsync({
                title: urlTitle.trim(),
                source_url: url.trim(),
                project_ids: urlProjectIds.length > 0 ? urlProjectIds : undefined,
            }), {
                loading: 'Adding PDF link...',
                success: 'PDF link added successfully',
                error: 'Failed to add PDF link',
            });
            handleOpenChange(false);
        } catch {
            // error already shown by toast
        }
    };

    const handleUrlChange = (value: string) => {
        setUrl(value);
        if (checkResult || checkError) {
            setCheckResult(null);
            setCheckError(null);
        }
    };

    const handleCheckUrl = async () => {
        if (!url.trim()) return;
        setCheckResult(null);
        setCheckError(null);

        try {
            const result = await checkUrlMutation.mutateAsync(url.trim());
            setCheckResult(result);
            if (result.valid && result.title && !urlTitle.trim()) {
                setUrlTitle(result.title);
            }
        } catch (err) {
            setCheckError(err instanceof Error ? err.message : 'Failed to check URL');
        }
    };

    const isUploading = uploadMutation.isPending;
    const isLinking = linkMutation.isPending;

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Add PDF</DialogTitle>
                    <DialogDescription>
                        Upload a PDF file or add a link to an external PDF.
                    </DialogDescription>
                </DialogHeader>

                <Tabs defaultValue="upload" className="mt-2">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="upload" className="gap-2">
                            <Upload className="h-4 w-4" />
                            Upload File
                        </TabsTrigger>
                        <TabsTrigger value="url" className="gap-2">
                            <LinkIcon className="h-4 w-4" />
                            Add URL
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="upload" className="space-y-4 mt-4">
                        {/* Dropzone */}
                        <div
                            {...getRootProps()}
                            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                                isDragActive
                                    ? 'border-primary bg-primary/10'
                                    : file
                                      ? 'border-primary/50 bg-primary/5'
                                      : 'border-muted-foreground/25 hover:border-primary/50'
                            }`}
                        >
                            <input {...getInputProps()} />
                            {file ? (
                                <div className="flex flex-col items-center gap-1 text-sm">
                                    <Upload className="h-6 w-6 text-primary mb-1" />
                                    <p className="font-medium text-foreground truncate max-w-full">{file.name}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {(file.size / 1024 / 1024).toFixed(2)} MB — click or drop to replace
                                    </p>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-1 text-muted-foreground">
                                    <Upload className="h-6 w-6 mb-1" />
                                    <p className="text-sm font-medium text-foreground">
                                        {isDragActive ? 'Drop the PDF here' : 'Drag & drop a PDF here'}
                                    </p>
                                    <p className="text-xs">or click to select a file</p>
                                </div>
                            )}
                        </div>

                        {/* Title */}
                        <div className="space-y-2">
                            <Label htmlFor="upload-title">Title</Label>
                            <Input
                                id="upload-title"
                                placeholder="Enter a title for this PDF"
                                value={uploadTitle}
                                onChange={(e) => setUploadTitle(e.target.value)}
                            />
                        </div>

                        {/* Projects */}
                        <ProjectPicker selectedIds={uploadProjectIds} onChange={setUploadProjectIds} />

                        {/* Submit */}
                        <Button
                            className="w-full"
                            onClick={handleUpload}
                            disabled={!file || !uploadTitle.trim() || isUploading}
                        >
                            {isUploading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Uploading...
                                </>
                            ) : (
                                'Upload'
                            )}
                        </Button>
                    </TabsContent>

                    <TabsContent value="url" className="space-y-4 mt-4">
                        {/* URL + Check button */}
                        <div className="space-y-2">
                            <Label htmlFor="pdf-url">PDF URL</Label>
                            <div className="flex gap-2">
                                <Input
                                    id="pdf-url"
                                    type="url"
                                    placeholder="https://arxiv.org/pdf/2301.00001.pdf"
                                    value={url}
                                    onChange={(e) => handleUrlChange(e.target.value)}
                                    className="flex-1"
                                />
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleCheckUrl}
                                    disabled={!url.trim() || checkUrlMutation.isPending}
                                >
                                    {checkUrlMutation.isPending ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        'Check'
                                    )}
                                </Button>
                            </div>

                            {/* Inline status */}
                            {checkUrlMutation.isPending && (
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    Checking URL...
                                </div>
                            )}
                            {checkResult?.valid && (
                                <div className="flex items-center gap-2 text-xs text-green-600">
                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                                    <span>
                                        Valid PDF — {checkResult.page_count ?? '?'} pages, {formatFileSize(checkResult.file_size)} — viewable in browser
                                    </span>
                                </div>
                            )}
                            {checkResult?.cors_blocked && (
                                <div className="flex items-start gap-2 text-xs text-amber-600">
                                    <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                                    <div>
                                        <p className="font-medium">{checkResult.error}</p>
                                        {checkResult.suggestions && (
                                            <ul className="mt-1 space-y-0.5 text-muted-foreground">
                                                {checkResult.suggestions.map((s, i) => (
                                                    <li key={i}>• {s}</li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                </div>
                            )}
                            {checkResult && !checkResult.valid && !checkResult.cors_blocked && (
                                <div className="flex items-center gap-2 text-xs text-destructive">
                                    <XCircle className="h-3.5 w-3.5 shrink-0" />
                                    <span>{checkResult.error}</span>
                                </div>
                            )}
                            {checkError && (
                                <div className="flex items-center gap-2 text-xs text-destructive">
                                    <XCircle className="h-3.5 w-3.5 shrink-0" />
                                    <span>{checkError}</span>
                                </div>
                            )}
                        </div>

                        {/* Title */}
                        <div className="space-y-2">
                            <Label htmlFor="url-title">Title</Label>
                            <Input
                                id="url-title"
                                placeholder="Enter a title for this PDF"
                                value={urlTitle}
                                onChange={(e) => setUrlTitle(e.target.value)}
                            />
                        </div>

                        {/* Projects */}
                        <ProjectPicker selectedIds={urlProjectIds} onChange={setUrlProjectIds} />

                        {/* Submit */}
                        <Button
                            className="w-full"
                            onClick={handleLink}
                            disabled={!url.trim() || !urlTitle.trim() || isLinking || !checkResult?.valid}
                        >
                            {isLinking ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Adding...
                                </>
                            ) : (
                                'Add PDF'
                            )}
                        </Button>
                    </TabsContent>
                </Tabs>
            </DialogContent>
        </Dialog>
    );
};
