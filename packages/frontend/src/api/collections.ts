import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

interface Collection {
    id: string;
    user_id: string;
    name: string;
    parent_id: string | null;
    position: number;
    created_at: string;
}

export const useCollections = () => {
    return useQuery({
        queryKey: ['collections'],
        queryFn: (): Promise<Collection[]> => apiFetch('/collections'),
    });
};

export const useCreateCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: Partial<Collection>): Promise<Collection> => {
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
        mutationFn: async ({ pdfId, collectionId }: { pdfId: string; collectionId: string }): Promise<void> => {
            await apiFetch(`/collections/${collectionId}/pdfs?pdf_id=${pdfId}`, { method: 'POST' });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};

export const useRemovePdfFromCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ pdfId, collectionId }: { pdfId: string; collectionId: string }): Promise<void> => {
            await apiFetch(`/collections/${collectionId}/pdfs/${pdfId}`, {
                method: 'DELETE',
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};
