import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload } from 'lucide-react';
import { useUploadPdf } from '@/api/pdfs';
import { toast } from 'sonner';

export const UploadDropzone = () => {
    const uploadMutation = useUploadPdf();

    const onDrop = useCallback((acceptedFiles: File[]) => {
        acceptedFiles.forEach((file) => {
            if (file.type !== 'application/pdf') {
                toast.error(`${file.name} is not a valid PDF file`);
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('title', file.name.replace('.pdf', ''));

            const promise = uploadMutation.mutateAsync(formData);

            toast.promise(promise, {
                loading: `Uploading ${file.name}...`,
                success: `Successfully uploaded ${file.name}`,
                error: `Failed to upload ${file.name}`,
            });
        });
    }, [uploadMutation]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: { 'application/pdf': ['.pdf'] }
    });

    return (
        <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
        ${isDragActive ? 'border-primary bg-primary/10' : 'border-muted-foreground/25 hover:border-primary/50'}`}
        >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
                <Upload className="h-8 w-8 mb-2" />
                {isDragActive ? (
                    <p>Drop the PDFs here ...</p>
                ) : (
                    <div>
                        <p className="font-medium text-foreground">Drag & drop PDFs here</p>
                        <p className="text-sm">or click to select files</p>
                    </div>
                )}
            </div>
        </div>
    );
};
