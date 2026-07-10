import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from './client';

export interface PdfSummary {
    pdf_id: string;
    status: 'not_generated' | 'generating' | 'complete' | 'failed';
    progress_pct: number;
    error_message: string | null;
    tldr: string | null;
    problem: string | null;
    method: string | null;
    dataset: string | null;
    result: string | null;
    contribution: string | null;
    key_claims: string[] | null;
    edited_fields: string[];
    model: string | null;
    generated_at: string | null;
    updated_at: string | null;
}

export interface ComparisonRow {
    pdf_id: string;
    title: string;
    year: number | null;
    summary: PdfSummary | null;
}

export interface ComparisonResponse {
    rows: ComparisonRow[];
    missing_count: number;
}

export interface BulkSummarizeResponse {
    queued: string[];
    skipped_complete: number;
    skipped_quota: number;
    total_papers: number;
}

const isActive = (s?: PdfSummary | null) => s?.status === 'generating';

// 404 = no summary row yet -> resolve to null instead of erroring.
const fetchSummaryOrNull = async (pdfId: string): Promise<PdfSummary | null> => {
    try {
        return await apiFetch<PdfSummary>(`/pdfs/${pdfId}/summary`);
    } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
    }
};

export const usePdfSummary = (pdfId: string | null, enabled = true) => {
    return useQuery({
        queryKey: ['pdf-summary', pdfId],
        queryFn: () => fetchSummaryOrNull(pdfId!),
        enabled: !!pdfId && enabled,
        refetchInterval: (query) =>
            isActive(query.state.data as PdfSummary | null) ? 2000 : false,
    });
};

export const useGeneratePdfSummary = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (pdfId: string): Promise<PdfSummary> =>
            apiFetch<PdfSummary>(`/pdfs/${pdfId}/summary`, { method: 'POST' }),
        onSuccess: (data) => {
            queryClient.setQueryData(['pdf-summary', data.pdf_id], data);
        },
    });
};

export const useUpdatePdfSummary = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({
            pdfId,
            ...patch
        }: { pdfId: string } & Partial<PdfSummary>): Promise<PdfSummary> =>
            apiFetch<PdfSummary>(`/pdfs/${pdfId}/summary`, {
                method: 'PATCH',
                body: JSON.stringify(patch),
            }),
        onSuccess: (data) => {
            queryClient.setQueryData(['pdf-summary', data.pdf_id], data);
            queryClient.invalidateQueries({ queryKey: ['collection-comparison'] });
        },
    });
};

export const useBulkSummarizeCollection = () => {
    const queryClient = useQueryClient();
    return useMutation<BulkSummarizeResponse, Error, string>({
        mutationFn: (collectionId: string) =>
            apiFetch<BulkSummarizeResponse>(
                `/collections/${collectionId}/summaries`,
                { method: 'POST' },
            ),
        onSuccess: (_data, collectionId) => {
            queryClient.invalidateQueries({
                queryKey: ['collection-comparison', collectionId],
            });
            queryClient.invalidateQueries({
                queryKey: ['collection-summaries', collectionId],
            });
        },
    });
};

// Poll while any member summary is still generating.
export const useCollectionSummaries = (collectionId: string | null) => {
    return useQuery({
        queryKey: ['collection-summaries', collectionId],
        queryFn: (): Promise<PdfSummary[]> =>
            apiFetch<PdfSummary[]>(`/collections/${collectionId}/summaries`),
        enabled: !!collectionId,
        refetchInterval: (query) => {
            const data = query.state.data as PdfSummary[] | undefined;
            return data?.some(isActive) ? 2500 : false;
        },
    });
};

export const useCollectionComparison = (collectionId: string | null) => {
    return useQuery({
        queryKey: ['collection-comparison', collectionId],
        queryFn: (): Promise<ComparisonResponse> =>
            apiFetch<ComparisonResponse>(`/collections/${collectionId}/comparison`),
        enabled: !!collectionId,
        refetchInterval: (query) => {
            const data = query.state.data as ComparisonResponse | undefined;
            return data?.rows.some((r) => isActive(r.summary)) ? 2500 : false;
        },
    });
};
