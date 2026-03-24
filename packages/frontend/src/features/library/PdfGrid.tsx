import { Pdf } from '@/api/pdfs';
import { PdfCard } from './PdfCard';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { Search } from 'lucide-react';

interface PdfGridProps {
    pdfs: Pdf[];
    isLoading: boolean;
    onDelete?: (id: string) => void;
    onEdit?: (pdf: Pdf) => void;
    onManageProjects?: (pdf: Pdf) => void;
    searchQuery?: string;
}

export const PdfGrid = ({ pdfs, isLoading, onDelete, onEdit, onManageProjects, searchQuery }: PdfGridProps) => {
    if (isLoading) {
        return (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                {[...Array(10)].map((_, i) => (
                    <div key={i} className="flex flex-col gap-4">
                        <Skeleton className="aspect-[3/4] w-full rounded-xl" />
                        <Skeleton className="h-4 w-3/4 rounded" />
                        <Skeleton className="h-3 w-1/2 rounded" />
                        <div className="flex gap-2 mt-2">
                            <Skeleton className="h-6 w-16 rounded-full" />
                            <Skeleton className="h-6 w-16 rounded-full" />
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    if (pdfs.length === 0) {
        return (
            <EmptyState
                icon={<Search className="w-8 h-8" />}
                title="No PDFs found"
                description={searchQuery ? `We couldn't find anything matching "${searchQuery}".` : "Your library is empty. Upload a PDF to get started."}
            />
        );
    }

    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-6">
            {pdfs.map((pdf) => (
                <PdfCard
                    key={pdf.id}
                    pdf={pdf}
                    onDelete={onDelete}
                    onEdit={onEdit}
                    onManageProjects={onManageProjects}
                />
            ))}
        </div>
    );
};
