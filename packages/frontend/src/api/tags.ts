import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

export interface Tag {
    id: string;
    user_id: string;
    name: string;
    color: string;
}

// Queries
export const useTags = () => {
    return useQuery({
        queryKey: ['tags'],
        queryFn: (): Promise<Tag[]> => apiFetch('/tags'),
    });
};

// Mutations
export const useCreateTag = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: Partial<Tag>): Promise<Tag> => {
            return apiFetch('/tags', {
                method: 'POST',
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tags'] });
        },
    });
};

export const useUpdateTag = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, data }: { id: string; data: Partial<Tag> }): Promise<Tag> => {
            return apiFetch(`/tags/${id}`, {
                method: 'PATCH',
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tags'] });
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};

export const useDeleteTag = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string): Promise<void> => {
            await apiFetch(`/tags/${id}`, {
                method: 'DELETE',
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tags'] });
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};

// Relationship Mutations
export const useAddTagToPdf = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ pdfId, tagId }: { pdfId: string; tagId: string }): Promise<void> => {
            await apiFetch(`/tags/pdfs/${pdfId}/tags/${tagId}`, {
                method: 'POST',
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};

export const useRemoveTagFromPdf = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ pdfId, tagId }: { pdfId: string; tagId: string }): Promise<void> => {
            await apiFetch(`/tags/pdfs/${pdfId}/tags/${tagId}`, {
                method: 'DELETE',
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};
