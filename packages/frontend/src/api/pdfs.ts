import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

export interface Pdf {
    id: string;
    user_id: string;
    title: string;
    filename: string;
    source_url?: string | null;
    github_sha?: string;
    file_size?: number;
    page_count?: number;
    doi?: string;
    isbn?: string;
    uploaded_at: string;
    updated_at: string;
}

export interface PdfListParams {
    collection_id?: string | null;
    tag_id?: string | null;
    q?: string;
    sort?: string;
    page?: number;
    per_page?: number;
}

export interface PdfLinkPayload {
    title: string;
    source_url: string;
    project_ids?: string[];
    doi?: string;
    isbn?: string;
}

// Queries
export const usePdfs = (params: PdfListParams) => {
    return useQuery({
        queryKey: ['pdfs', params],
        queryFn: async (): Promise<Pdf[]> => {
            const searchParams = new URLSearchParams();
            if (params.collection_id) searchParams.append('collection_id', params.collection_id);
            if (params.tag_id) searchParams.append('tag_id', params.tag_id);
            if (params.q) searchParams.append('q', params.q);
            if (params.sort) searchParams.append('sort', params.sort);
            if (params.page) searchParams.append('page', params.page.toString());
            if (params.per_page) searchParams.append('per_page', params.per_page.toString());

            const query = searchParams.toString();
            return apiFetch(`/pdfs${query ? `?${query}` : ''}`);
        },
    });
};

export const usePdf = (id: string) => {
    return useQuery({
        queryKey: ['pdfs', id],
        queryFn: (): Promise<Pdf> => apiFetch(`/pdfs/${id}`),
        enabled: !!id,
    });
};

export const usePdfCollections = (id: string) => {
    return useQuery({
        queryKey: ['pdfs', id, 'collections'],
        queryFn: (): Promise<{ collection_ids: string[] }> => apiFetch(`/pdfs/${id}/collections`),
        enabled: !!id,
    });
};

export const usePdfContent = (id: string) => {
    return useQuery({
        queryKey: ['pdfs', id, 'content'],
        queryFn: async (): Promise<Blob> => {
            const { apiFetchBlob } = await import('./client');
            return apiFetchBlob(`/pdfs/${id}/content`);
        },
        enabled: !!id,
        staleTime: Infinity, // PDFs rarely change content, mostly metadata
    });
};

// Mutations
export const useUploadPdf = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (formData: FormData): Promise<Pdf> => {
            // Custom fetch because we are sending FormData, not JSON
            return apiFetch('/pdfs/upload', {
                method: 'POST',
                headers: {
                    // Do not set Content-Type here, let the browser set it with the boundary for multipart/form-data
                },
                body: formData,
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};

export const useLinkPdf = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: PdfLinkPayload): Promise<Pdf> => {
            return apiFetch('/pdfs/link', {
                method: 'POST',
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};

export const useUpdatePdf = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, data }: { id: string; data: Partial<Pdf> }): Promise<Pdf> => {
            return apiFetch(`/pdfs/${id}`, {
                method: 'PATCH',
                body: JSON.stringify(data),
            });
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
            queryClient.invalidateQueries({ queryKey: ['pdfs', variables.id] });
        },
    });
};

export const useDeletePdf = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string): Promise<void> => {
            await apiFetch(`/pdfs/${id}`, {
                method: 'DELETE',
            });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
        },
    });
};
