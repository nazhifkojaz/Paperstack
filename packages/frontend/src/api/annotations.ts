import { useMemo, useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

export interface AnnotationSet {
    id: string;
    pdf_id: string;
    user_id: string;
    name: string;
    color: string;
    source?: string | null;  // 'manual' | 'auto_highlight'
    created_at: string;
    updated_at: string;
}

export interface Annotation {
    id: string;
    set_id: string;
    page_number: number;
    type: 'highlight' | 'rect' | 'note';
    rects: Array<{ x: number, y: number, w: number, h: number }>;
    selected_text?: string | null;
    note_content?: string | null;
    color?: string | null;
    metadata?: Record<string, any> | null;
    created_at: string;
    updated_at: string;
}

// --- Queries ---

export const useAnnotationSets = (pdfId: string) => {
    return useQuery({
        queryKey: ['annotation_sets', pdfId],
        queryFn: (): Promise<AnnotationSet[]> => apiFetch(`/annotations/sets?pdf_id=${pdfId}`),
        enabled: !!pdfId,
    });
};

export const useAnnotations = (setId: string | null) => {
    return useQuery({
        queryKey: ['annotations', setId],
        queryFn: (): Promise<Annotation[]> => apiFetch(`/annotations/sets/${setId}/items`),
        enabled: !!setId,
    });
};

export const useMultiSetAnnotations = (setIds: string[]) => {
    const queries = useQueries({
        queries: setIds.map(id => ({
            queryKey: ['annotations', id],
            queryFn: (): Promise<Annotation[]> => apiFetch(`/annotations/sets/${id}/items`),
            enabled: !!id,
        })),
    });

    // Memoize to prevent re-computation on every render
    const allAnnotations = useMemo(() => {
        return queries
            .filter(q => q.isSuccess && q.data)
            .flatMap(q => q.data!);
    }, [queries]);

    const isLoading = queries.some(q => q.isLoading);

    return { data: allAnnotations, isLoading };
};

// --- Mutations ---

export const useCreateAnnotationSet = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: { pdf_id: string, name: string, color?: string }): Promise<AnnotationSet> =>
            apiFetch('/annotations/sets', { method: 'POST', body: JSON.stringify(data) }),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['annotation_sets', variables.pdf_id] });
        },
    });
};

export const useUpdateAnnotationSet = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: Partial<AnnotationSet> }): Promise<AnnotationSet> =>
            apiFetch(`/annotations/sets/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['annotation_sets'] });
        },
    });
};

export const useDeleteAnnotationSet = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string): Promise<void> =>
            apiFetch(`/annotations/sets/${id}`, { method: 'DELETE' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['annotation_sets'] });
        },
    });
};

export const useCreateAnnotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: Partial<Annotation> & { set_id: string, page_number: number, type: string, rects: any }): Promise<Annotation> =>
            apiFetch('/annotations/items', { method: 'POST', body: JSON.stringify(data) }),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['annotations', variables.set_id] });
        },
    });
};

export const useUpdateAnnotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, data }: { id: string, data: Partial<Annotation> }): Promise<Annotation> =>
            apiFetch(`/annotations/items/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
        onSuccess: (result) => {
            queryClient.invalidateQueries({ queryKey: ['annotations', result.set_id] });
        },
    });
};

export const useDeleteAnnotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, setId }: { id: string, setId: string }): Promise<void> =>
            apiFetch(`/annotations/items/${id}`, { method: 'DELETE' }),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['annotations', variables.setId] });
        },
    });
};
