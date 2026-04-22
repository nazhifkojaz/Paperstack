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

// Queries
export const useCollections = () => {
    return useQuery({
        queryKey: ['collections'],
        queryFn: (): Promise<Collection[]> => apiFetch('/collections'),
    });
};

// Mutations
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

// Relationship Mutations
export const useAddPdfToCollection = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ pdfId, collectionId }: { pdfId: string; collectionId: string }): Promise<void> => {
            // pdf_id is a FastAPI query param (not path), so it must be sent as ?pdf_id=
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
