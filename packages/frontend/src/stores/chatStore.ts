import { create } from 'zustand';
import type { ContextChunk } from '@/api/chat';

interface StreamingMessage {
    id: string;
    content: string;
    isStreaming: boolean;
    contextChunks: ContextChunk[];
}

interface ChatStore {
    isChatPanelOpen: boolean;
    toggleChatPanel: () => void;

    activeConversationId: string | null;
    setActiveConversationId: (id: string | null) => void;

    streamingMessage: StreamingMessage | null;
    startStreaming: (tempId: string) => void;
    appendToken: (token: string) => void;
    finalizeStreaming: (messageId: string, chunks: ContextChunk[]) => void;
    clearStreaming: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
    isChatPanelOpen: false,
    toggleChatPanel: () => set((s) => ({ isChatPanelOpen: !s.isChatPanelOpen })),

    activeConversationId: null,
    setActiveConversationId: (id) => set({ activeConversationId: id }),

    streamingMessage: null,
    startStreaming: (tempId) =>
        set({ streamingMessage: { id: tempId, content: '', isStreaming: true, contextChunks: [] } }),
    appendToken: (token) =>
        set((s) => ({
            streamingMessage: s.streamingMessage
                ? { ...s.streamingMessage, content: s.streamingMessage.content + token }
                : null,
        })),
    finalizeStreaming: (messageId, chunks) =>
        set((s) => ({
            streamingMessage: s.streamingMessage
                ? { ...s.streamingMessage, id: messageId, isStreaming: false, contextChunks: chunks }
                : null,
        })),
    clearStreaming: () => set({ streamingMessage: null }),
}));
