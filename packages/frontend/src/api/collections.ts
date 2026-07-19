import { useQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { apiFetch, apiFetchBlob } from './client';
import { downloadBlob } from '@/lib/download-utils';
import { toast } from 'sonner';

interface Collection {
    id: string;
    user_id: string;
    name: string;
    parent_id: string | null;
    position: number;
    created_at: string;
}

export interface CreateCollectionInput {
    name: string;
    parent_id?: string | null;
    position?: number;
}

interface PdfCollectionInput {
    pdfId: string;
    collectionId: string;
}

const invalidateCollectionMembershipQueries = (
    queryClient: QueryClient,
    collectionId: string,
) => {
    queryClient.invalidateQueries({ queryKey: ['pdfs'] });
    queryClient.invalidateQueries({ queryKey: ['collections'] });
    queryClient.invalidateQueries({ queryKey: ['collection-overview', collectionId] });
    queryClient.invalidateQueries({ queryKey: ['collection-comparison', collectionId] });
    queryClient.invalidateQueries({ queryKey: ['collection-summaries', collectionId] });
    queryClient.invalidateQueries({ queryKey: ['collection-insight', collectionId] });
    queryClient.invalidateQueries({ queryKey: ['collection-recommendations', collectionId] });
    queryClient.invalidateQueries({ queryKey: ['collection-duplicates', collectionId] });
};

export const useCollections = () => {
    return useQuery({
        queryKey: ['collections'],
        queryFn: (): Promise<Collection[]> => apiFetch('/collections'),
    });
};

export const useCreateCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: CreateCollectionInput): Promise<Collection> => {
            return apiFetch('/collections', {
                method: 'POST',
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['collections'] });
        },
    });
};

export const useAddPdfToCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ pdfId, collectionId }: PdfCollectionInput): Promise<void> => {
            await apiFetch(`/collections/${collectionId}/pdfs?pdf_id=${pdfId}`, { method: 'POST' });
        },
        onSuccess: (_data, variables) => {
            invalidateCollectionMembershipQueries(queryClient, variables.collectionId);
        },
    });
};

export const useRemovePdfFromCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ pdfId, collectionId }: PdfCollectionInput): Promise<void> => {
            await apiFetch(`/collections/${collectionId}/pdfs/${pdfId}`, {
                method: 'DELETE',
            });
        },
        onSuccess: (_data, variables) => {
            invalidateCollectionMembershipQueries(queryClient, variables.collectionId);
        },
    });
};

export const useUpdateCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            id,
            ...data
        }: { id: string; name?: string; parent_id?: string | null; position?: number }): Promise<Collection> => {
            return apiFetch(`/collections/${id}`, {
                method: 'PATCH',
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['collections'] });
        },
    });
};

export const useSwapCollectionPositions = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ firstId, secondId }: { firstId: string; secondId: string }): Promise<Collection[]> => {
            return apiFetch('/collections/swap-positions', {
                method: 'POST',
                body: JSON.stringify({ first_id: firstId, second_id: secondId }),
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['collections'] });
        },
    });
};

export const useDeleteCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string): Promise<void> => {
            await apiFetch(`/collections/${id}`, {
                method: 'DELETE',
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['collections'] });
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
            queryClient.invalidateQueries({ queryKey: ['collection-overview'] });
        },
    });
};

export const useExportCollection = () => {
    return useMutation<Blob, Error, { id: string; format?: 'bibtex' | 'markdown' }>({
        mutationFn: async ({ id, format = 'bibtex' }) => {
            return apiFetchBlob(`/collections/${id}/export?format=${format}`);
        },
        onSuccess: (blob, { format }) => {
            const ext = format === 'markdown' ? 'md' : 'bib';
            downloadBlob(blob, `collection.${ext}`);
        },
        onError: (error) => {
            toast.error(error.message || 'Export failed');
        },
    });
};

export interface CollectionOverviewPaper {
    id: string;
    title: string;
    year: number | null;
    first_author: string | null;
}

interface CollectionOverview {
    paper_count: number;
    indexed_count: number;
    year_distribution: Record<string, number>;
    top_authors: { name: string; count: number }[];
    recent_papers: { id: string; title: string; filename: string }[];
    papers: CollectionOverviewPaper[];
}

export const useCollectionOverview = (collectionId: string | null) => {
    return useQuery<CollectionOverview>({
        queryKey: ['collection-overview', collectionId],
        queryFn: () => apiFetch(`/collections/${collectionId}/overview`),
        enabled: !!collectionId,
    });
};
