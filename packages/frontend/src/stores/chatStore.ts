import { create } from 'zustand';
import type { ContextChunk } from '@/api/chat';

interface StreamingMessage {
    id: string;
    role: 'assistant';
    content: string;
    isStreaming: boolean;
    context_chunks: ContextChunk[] | null;
    error: string | null;
}

interface ChatStore {
    isChatPanelOpen: boolean;
    toggleChatPanel: () => void;
    setChatPanelOpen: (open: boolean) => void;

    isChatFullscreen: boolean;
    toggleChatFullscreen: () => void;
    setChatFullscreen: (fullscreen: boolean) => void;

    activeConversationId: string | null;
    setActiveConversationId: (id: string | null) => void;

    streamingMessage: StreamingMessage | null;
    startStreaming: (tempId: string) => void;
    appendToken: (token: string) => void;
    finalizeStreaming: (messageId: string, chunks: ContextChunk[]) => void;
    streamingFailed: (error: string) => void;
    clearStreaming: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
    isChatPanelOpen: false,
    toggleChatPanel: () => set((s) => ({ isChatPanelOpen: !s.isChatPanelOpen })),
    setChatPanelOpen: (open) => set({ isChatPanelOpen: open }),

    isChatFullscreen: false,
    toggleChatFullscreen: () => set((s) => ({ isChatFullscreen: !s.isChatFullscreen })),
    setChatFullscreen: (fullscreen) => set({ isChatFullscreen: fullscreen }),

    activeConversationId: null,
    setActiveConversationId: (id) => set({ activeConversationId: id }),

    streamingMessage: null,
    startStreaming: (tempId) =>
        set({ streamingMessage: { id: tempId, role: 'assistant', content: '', isStreaming: true, context_chunks: null, error: null } }),
    appendToken: (token) =>
        set((s) => ({
            streamingMessage: s.streamingMessage
                ? { ...s.streamingMessage, content: s.streamingMessage.content + token }
                : null,
        })),
    finalizeStreaming: (messageId, chunks) =>
        set((s) => ({
            streamingMessage: s.streamingMessage
                ? { ...s.streamingMessage, id: messageId, isStreaming: false, context_chunks: chunks }
                : null,
        })),
    streamingFailed: (error) =>
        set((s) => ({
            streamingMessage: s.streamingMessage
                ? { ...s.streamingMessage, isStreaming: false, error }
                : null,
        })),
    clearStreaming: () => set({ streamingMessage: null }),
}));
