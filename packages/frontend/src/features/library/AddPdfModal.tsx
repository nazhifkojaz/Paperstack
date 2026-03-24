import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, Link as LinkIcon, Loader2 } from 'lucide-react';
import { useUploadPdf, useLinkPdf } from '@/api/pdfs';
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

export const AddPdfModal = ({ open, onOpenChange }: AddPdfModalProps) => {
    // Upload File tab state
    const [file, setFile] = useState<File | null>(null);
    const [uploadTitle, setUploadTitle] = useState('');
    const [uploadProjectIds, setUploadProjectIds] = useState<string[]>([]);

    // Add URL tab state
    const [url, setUrl] = useState('');
    const [urlTitle, setUrlTitle] = useState('');
    const [urlProjectIds, setUrlProjectIds] = useState<string[]>([]);

    const uploadMutation = useUploadPdf();
    const linkMutation = useLinkPdf();

    const resetState = () => {
        setFile(null);
        setUploadTitle('');
        setUploadProjectIds([]);
        setUrl('');
        setUrlTitle('');
        setUrlProjectIds([]);
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
        if (!url.trim() || !urlTitle.trim()) return;

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
                        {/* URL */}
                        <div className="space-y-2">
                            <Label htmlFor="pdf-url">PDF URL</Label>
                            <Input
                                id="pdf-url"
                                type="url"
                                placeholder="https://arxiv.org/pdf/2301.00001.pdf"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">
                                Direct link to a PDF file. The PDF will be loaded from this URL each time you open it.
                            </p>
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
                            disabled={!url.trim() || !urlTitle.trim() || isLinking}
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
