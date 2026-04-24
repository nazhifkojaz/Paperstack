import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

interface AutoHighlightRequest {
    pdf_id: string;
    categories: string[];
    pages?: number[];
}

interface AutoHighlightResponse {
    cache_id: string;
    annotation_set_id: string | null;
    from_cache: boolean;
    highlights_count: number;
    pages_analyzed: string;
    provider_fallback?: boolean;
}

interface AutoHighlightCacheEntry {
    id: string;
    categories: string[];
    pages: number[];
    status: 'pending' | 'complete' | 'failed';
    created_at: string;
    annotation_set_id: string | null;
}

interface QuotaInfo {
    free_uses_remaining: number;
    has_own_key: boolean;
    providers: string[];
}

interface ApiKeyCreate {
    provider: 'glm' | 'gemini';
    api_key: string;
}

interface ApiKeyResponse {
    provider: string;
    key_preview: string;
    created_at: string;
}

export const useAutoHighlightQuota = () => {
    return useQuery({
        queryKey: ['auto-highlight-quota'],
        queryFn: (): Promise<QuotaInfo> => apiFetch('/auto-highlight/quota'),
    });
};

export const useAnalyzePaper = () => {
    return useMutation({
        mutationFn: (data: AutoHighlightRequest): Promise<AutoHighlightResponse> =>
            apiFetch('/auto-highlight/analyze', {
                method: 'POST',
                body: JSON.stringify(data),
            }),
    });
};

export const useAnalysisStatus = (cacheId: string | null) => {
    return useQuery({
        queryKey: ['analysis-status', cacheId],
        queryFn: (): Promise<AutoHighlightCacheEntry> =>
            apiFetch(`/auto-highlight/cache/entry/${cacheId}`),
        enabled: !!cacheId,
        refetchInterval: (query) => {
            const data = query.state.data as AutoHighlightCacheEntry | undefined;
            // Keep polling if we haven't gotten a terminal status yet
            if (!data || data.status === 'pending') return 2000;
            return false;
        },
        retry: 3,
    });
};

export const useCreateApiKey = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: ApiKeyCreate): Promise<ApiKeyResponse> =>
            apiFetch('/settings/api-keys', {
                method: 'POST',
                body: JSON.stringify(data),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
        },
    });
};

export const useDeleteApiKey = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (provider: string): Promise<void> =>
            apiFetch(`/settings/api-keys/${provider}`, { method: 'DELETE' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
        },
    });
};
