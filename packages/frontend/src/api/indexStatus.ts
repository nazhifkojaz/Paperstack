import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

export type IndexStatus = {
    status: 'not_indexed' | 'indexing' | 'indexed' | 'failed';
    chunk_count?: number | null;
    error_message?: string | null;
    indexed_at?: string | null;
};

export function useIndexStatus(pdfId: string | undefined) {
    return useQuery({
        queryKey: ['pdf-index-status', pdfId],
        queryFn: (): Promise<IndexStatus> =>
            apiFetch(`/pdfs/${pdfId}/index-status`),
        enabled: !!pdfId,
        refetchInterval: (query) => {
            const data = query.state.data as IndexStatus | undefined;
            if (!data || data.status === 'indexing' || data.status === 'not_indexed') return 3000;
            return false;
        },
    });
}

export function useReindexPdf(pdfId: string | undefined) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (): Promise<{ status: string }> =>
            apiFetch(`/pdfs/${pdfId}/reindex`, { method: 'POST' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['pdf-index-status', pdfId] });
        },
    });
}
