import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiFetchBlob } from './client';

export interface Citation {
    id: string;
    pdf_id: string;
    user_id: string;
    doi: string | null;
    title: string | null;
    authors: string | null;
    year: number | null;
    bibtex: string;
    csl_json: object | null;
    source: string;
    created_at: string;
    updated_at: string;
}

export interface CitationUpdate {
    doi?: string;
    title?: string;
    authors?: string;
    year?: number;
    bibtex?: string;
    csl_json?: object;
    source?: string;
}

// ─── Queries ─────────────────────────────────────────────────────────────────

export const useCitation = (pdfId: string) =>
    useQuery<Citation>({
        queryKey: ['citation', pdfId],
        queryFn: () => apiFetch(`/pdfs/${pdfId}/citation`),
        enabled: !!pdfId,
        retry: false, // 404 is expected when no citation exists yet
    });

// ─── Mutations ────────────────────────────────────────────────────────────────

export const useAutoExtractCitation = (pdfId: string) => {
    const qc = useQueryClient();
    return useMutation<Citation>({
        mutationFn: () =>
            apiFetch(`/pdfs/${pdfId}/citation/auto`, { method: 'POST' }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['citation', pdfId] });
        },
    });
};

export const useUpdateCitation = (pdfId: string) => {
    const qc = useQueryClient();
    return useMutation<Citation, Error, CitationUpdate>({
        mutationFn: (data) =>
            apiFetch(`/pdfs/${pdfId}/citation`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['citation', pdfId] });
        },
    });
};

// ─── Bulk Operations ────────────────────────────────────────────────────────────

export interface BulkExportRequest {
    pdf_ids: string[];
    format?: 'bibtex' | 'json';
}

export interface ValidateResponse {
    has_citation: string[];
    missing: string[];
}

export const useValidateCitations = () => {
    return useMutation<ValidateResponse, Error, string[]>({
        mutationFn: async (pdfIds) => {
            return apiFetch<ValidateResponse>('/citations/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pdf_ids: pdfIds }),
            });
        },
    });
};

export const useBulkExportCitations = () => {
    return useMutation<Blob, Error, BulkExportRequest>({
        mutationFn: async (request) => {
            return apiFetchBlob(`/citations/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request),
            });
        },
        onSuccess: (blob) => {
            // Trigger browser download
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `citations-${new Date().toISOString().split('T')[0]}.bib`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        },
    });
};
