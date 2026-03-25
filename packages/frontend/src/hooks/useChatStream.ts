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
import { streamChat, type ChatMessage, type ContextChunk } from '@/api/chat';
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
    bottomRef: React.RefObject<HTMLDivElement>;
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

    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [indexError, setIndexError] = useState<string | null>(null);
    const [lastMessage, setLastMessage] = useState('');

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

        try {
            await streamChat({
                conversationId,
                message,
                onToken: (token) => appendToken(token),
                onDone: (messageId, chunks) => {
                    finalizeStreaming(messageId, chunks);
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
