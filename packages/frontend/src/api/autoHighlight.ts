import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';

// Types

interface AutoHighlightRequest {
    pdf_id: string;
    categories: string[];
    pages?: number[];
}

interface AutoHighlightResponse {
    annotation_set_id: string;
    from_cache: boolean;
    highlights_count: number;
    pages_analyzed: string;
    provider_fallback?: boolean;
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

// Auto-Highlight Hooks

export const useAutoHighlightQuota = () => {
    return useQuery({
        queryKey: ['auto-highlight-quota'],
        queryFn: (): Promise<QuotaInfo> => apiFetch('/auto-highlight/quota'),
    });
};

export const useAnalyzePaper = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: AutoHighlightRequest): Promise<AutoHighlightResponse> =>
            apiFetch('/auto-highlight/analyze', {
                method: 'POST',
                body: JSON.stringify(data),
            }),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['annotation_sets', variables.pdf_id] });
            queryClient.invalidateQueries({ queryKey: ['auto-highlight-cache', variables.pdf_id] });
            queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
        },
    });
};

// API Key Hooks

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
