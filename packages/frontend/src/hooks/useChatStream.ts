/**
 * React hook for managing chat streaming state and interactions.
 * Encapsulates the common streaming logic used across chat interfaces.
 *
 * @example
 * const { input, setInput, isSending, handleSend, handleKeyDown, displayMessages } =
 *     useChatStream({ conversationId, queryClient });
 */

import { useState, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { streamChat, type ContextChunk, type ChatMessage } from '@/api/chat';
import { useChatStore } from '@/stores/chatStore';

export interface StreamingMessage {
    id: string;
    role: 'assistant';
    content: string;
    context_chunks: ContextChunk[] | null;
    isStreaming: boolean;
}

export interface UseChatStreamOptions {
    /** The active conversation ID to send messages to */
    conversationId: string | null;
    /** Query keys to invalidate after streaming completes */
    invalidateQueryKeys?: readonly unknown[][];
    /** Optional callback when a message starts sending */
    onMessageStart?: () => void;
    /** Optional callback when an error occurs */
    onError?: (error: string, isQuotaError: boolean, isIndexError: boolean) => void;
}

export interface UseChatStreamReturn {
    // Input state
    input: string;
    setInput: (value: string) => void;

    // Sending state
    isSending: boolean;
    indexError: string | null;
    setIndexError: (error: string | null) => void;
    lastMessage: string;
    setLastMessage: (message: string) => void;

    // Streaming state (from store)
    streamingMessage: StreamingMessage | null;

    // Actions
    handleSend: (overrideMessage?: string) => Promise<void>;
    handleRetry: () => void;
    handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
    clearStreaming: () => void;

    // Display
    bottomRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Hook for managing chat streaming state and interactions.
 * Uses the chatStore for streaming state to ensure consistency across chat UIs.
 */
export function useChatStream({
    conversationId,
    invalidateQueryKeys = [],
    onMessageStart,
    onError,
}: UseChatStreamOptions): UseChatStreamReturn {
    const queryClient = useQueryClient();
    const {
        streamingMessage,
        startStreaming,
        appendToken,
        finalizeStreaming,
        clearStreaming: clearStoreStreaming,
    } = useChatStore();

    const bottomRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [indexError, setIndexError] = useState<string | null>(null);
    const [lastMessage, setLastMessage] = useState('');

    // Abort any in-flight stream when the component unmounts
    useEffect(() => {
        return () => { abortControllerRef.current?.abort(); };
    }, []);

    const clearStreaming = () => {
        setIndexError(null);
        clearStoreStreaming();
    };

    const handleSend = async (overrideMessage?: string) => {
        const message = (overrideMessage ?? input).trim();
        if (!message || isSending || !conversationId) return;

        setInput('');
        setIndexError(null);
        setLastMessage(message);
        setIsSending(true);
        onMessageStart?.();

        const tempId = `temp-${Date.now()}`;
        startStreaming(tempId);

        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        let accumulatedContent = '';

        try {
            await streamChat({
                conversationId,
                message,
                signal: abortController.signal,
                onNotice: (msg) => toast.info(msg),
                onToken: (token) => { appendToken(token); accumulatedContent += token; },
                onDone: (messageId, chunks, providerFallback) => {
                    finalizeStreaming(messageId, chunks);
                    if (providerFallback) {
                        queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
                    }
                    // Optimistically add the assistant reply to the history cache immediately.
                    // This prevents it from disappearing when startStreaming() replaces
                    // streamingMessage on the next send before the invalidation refetch completes.
                    queryClient.setQueryData<ChatMessage[]>(
                        ['chat-history', conversationId],
                        (old = []) => [
                            ...old.filter(m => m.id !== messageId),
                            {
                                id: messageId,
                                role: 'assistant' as const,
                                content: accumulatedContent,
                                context_chunks: chunks,
                                created_at: new Date().toISOString(),
                            },
                        ]
                    );
                },
                onError: (err) => {
                    clearStreaming();
                    const errorMsg = err.message;
                    const isQuotaError = errorMsg.toLowerCase().includes('quota');
                    const isIndexError = errorMsg.toLowerCase().includes('index');

                    if (isQuotaError) {
                        toast.error('Chat quota exhausted. Add an API key in Settings.');
                    } else if (isIndexError) {
                        setIndexError(errorMsg);
                    } else {
                        toast.error(errorMsg);
                    }

                    onError?.(errorMsg, isQuotaError, isIndexError);
                },
            });

            // Stream is fully done — invalidate queries
            for (const key of invalidateQueryKeys) {
                queryClient.invalidateQueries({ queryKey: key });
            }
        } catch (err) {
            clearStreaming();
            // Ignore aborts caused by component unmount or navigation
            if (err instanceof Error && err.name === 'AbortError') return;
            const errorMsg = err instanceof Error ? err.message : 'Failed to send message';
            setIndexError(errorMsg);
            toast.error(errorMsg);
            onError?.(errorMsg, false, errorMsg.toLowerCase().includes('index'));
        } finally {
            setIsSending(false);
        }
    };

    const handleRetry = () => {
        if (lastMessage) handleSend(lastMessage);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // Auto-scroll to bottom when streaming content changes
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [streamingMessage?.content]);

    return {
        input,
        setInput,
        isSending,
        indexError,
        setIndexError,
        lastMessage,
        setLastMessage,
        streamingMessage,
        handleSend,
        handleRetry,
        handleKeyDown,
        clearStreaming,
        bottomRef,
    };
}
