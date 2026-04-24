import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';
import { useAuthStore } from '@/stores/authStore';
import { API_URL } from '@/lib/config';

// --- Types ---

export interface Conversation {
    id: string;
    pdf_id: string | null;
    collection_id: string | null;
    title: string | null;
    created_at: string;
    updated_at: string;
}

export interface ContextChunk {
    chunk_id: string;
    page_number: number;
    snippet: string;
    pdf_id?: string;
    pdf_title?: string;
    end_page_number?: number;
    section_title?: string;
    section_level?: number;
}

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    context_chunks: ContextChunk[] | null;
    created_at: string;
}

interface SemanticSearchRequest {
    query: string;
    collection_id?: string;
    limit?: number;
}

export interface SemanticSearchResult {
    pdf_id: string;
    pdf_title: string;
    page_number: number;
    snippet: string;
    score: number;
}

interface ExplainRequest {
    pdf_id: string;
    annotation_id: string;
    selected_text: string;
    page_number: number;
}

interface ExplainResponse {
    explanation: string;
    note_content: string;
    explain_uses_remaining: number;
    provider_fallback?: boolean;
}

// --- Hooks ---

export const useConversations = (pdfId?: string, collectionId?: string) => {
    const params = new URLSearchParams();
    if (pdfId) params.set('pdf_id', pdfId);
    if (collectionId) params.set('collection_id', collectionId);
    const query = params.toString() ? `?${params}` : '';

    return useQuery({
        queryKey: ['chat-conversations', pdfId, collectionId],
        queryFn: (): Promise<Conversation[]> =>
            apiFetch(`/chat/conversations${query}`),
        enabled: !!(pdfId || collectionId),
    });
};

export const useCreateConversation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: { pdf_id?: string; collection_id?: string }): Promise<Conversation> =>
            apiFetch('/chat/conversations', {
                method: 'POST',
                body: JSON.stringify(data),
            }),
        onSuccess: (conv) => {
            queryClient.invalidateQueries({
                queryKey: ['chat-conversations', conv.pdf_id, conv.collection_id],
            });
        },
    });
};

export const useChatHistory = (conversationId: string | null) => {
    return useQuery({
        queryKey: ['chat-history', conversationId],
        queryFn: (): Promise<ChatMessage[]> =>
            apiFetch(`/chat/conversations/${conversationId}/messages`),
        enabled: !!conversationId,
    });
};

export const useDeleteConversation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (conversationId: string): Promise<void> =>
            apiFetch(`/chat/conversations/${conversationId}`, { method: 'DELETE' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['chat-conversations'] });
        },
    });
};

export const useSemanticSearch = () => {
    return useMutation({
        mutationFn: (data: SemanticSearchRequest): Promise<SemanticSearchResult[]> =>
            apiFetch('/chat/semantic-search', {
                method: 'POST',
                body: JSON.stringify(data),
            }),
    });
};

export const useExplainAnnotation = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: ExplainRequest): Promise<ExplainResponse> =>
            apiFetch('/chat/explain', {
                method: 'POST',
                body: JSON.stringify(data),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['annotations'] });
        },
    });
};

export async function streamChat(params: {
    conversationId: string;
    message: string;
    onToken: (token: string) => void;
    onDone: (messageId: string, chunks: ContextChunk[], providerFallback: boolean) => void;
    onNotice?: (message: string) => void;
    onError: (err: Error) => void;
    signal?: AbortSignal;
}): Promise<void> {
    const token = useAuthStore.getState().accessToken;
    const res = await fetch(
        `${API_URL}/chat/conversations/${params.conversationId}/stream`,
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ content: params.message }),
            signal: params.signal,
        },
    );

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Chat request failed' }));
        params.onError(new Error(err.detail || `HTTP ${res.status}`));
        return;
    }

    if (!res.body) {
        params.onError(new Error('No response body received from server'));
        return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop()!;
        for (const part of parts) {
            if (!part.startsWith('data: ')) continue;
            try {
                const data = JSON.parse(part.slice(6));
                if (data.error) {
                    params.onError(new Error(data.error));
                    return;
                }
                if (data.notice) params.onNotice?.(data.notice);
                if (data.token) params.onToken(data.token);
                if (data.done) params.onDone(
                    data.message_id,
                    data.context_chunks ?? [],
                    data.provider_fallback ?? false,
                );
            } catch {
                // malformed SSE line — skip
            }
        }
    }
}
