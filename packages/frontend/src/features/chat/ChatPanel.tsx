import { useEffect, useState } from 'react';
import { MessageSquare, Plus, Send, Loader2, BookOpen, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

import { useChatStore } from '@/stores/chatStore';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import {
    useConversations,
    useCreateConversation,
    useDeleteConversation,
    useChatHistory,
    type Conversation,
} from '@/api/chat';
import { useChatStream } from '@/hooks/useChatStream';
import { ChatMessageList } from '@/components/chat/ChatMessageList';
import { DeleteConversationDialog } from './DeleteConversationDialog';

interface ChatPanelProps {
    pdfId: string;
}

export const ChatPanel = ({ pdfId }: ChatPanelProps) => {
    const { isChatPanelOpen, activeConversationId, setActiveConversationId } = useChatStore();
    const { setCurrentPage } = usePdfViewerStore();
    const queryClient = useQueryClient();

    const [deletingConv, setDeletingConv] = useState<{ id: string; title: string } | null>(null);

    const { data: conversations = [], isLoading: loadingConvs } = useConversations(pdfId);
    const createConversation = useCreateConversation();
    const { mutateAsync: deleteConversation, isPending: isDeletingConv } = useDeleteConversation();
    const { data: history = [] } = useChatHistory(activeConversationId);

    // Use the shared streaming hook
    const {
        input,
        setInput,
        isSending,
        indexError,
        setIndexError,
        handleSend,
        handleRetry,
        handleKeyDown,
        clearStreaming,
        bottomRef,
        streamingMessage,
    } = useChatStream({
        conversationId: activeConversationId,
        invalidateQueryKeys: [
            ['chat-history', activeConversationId],
            ['chat-conversations', pdfId, undefined],
        ],
        onMessageStart: () => setIndexError(null),
        onError: (error, _isQuotaError, isIndexError) => {
            if (isIndexError) {
                setIndexError(error);
            }
        },
    });

    // Auto-select first conversation or create one
    useEffect(() => {
        if (loadingConvs || !isChatPanelOpen) return;
        if (conversations.length > 0 && !activeConversationId) {
            setActiveConversationId(conversations[0].id);
        }
    }, [conversations, loadingConvs, activeConversationId, isChatPanelOpen, setActiveConversationId]);

    if (!isChatPanelOpen) return null;

    const handleNewConversation = async () => {
        try {
            const conv = await createConversation.mutateAsync({ pdf_id: pdfId });
            queryClient.setQueryData<Conversation[]>(
                ['chat-conversations', pdfId, undefined],
                (old = []) => [conv, ...old],
            );
            setActiveConversationId(conv.id);
            clearStreaming();
            setIndexError(null);
        } catch {
            toast.error('Failed to create conversation');
        }
    };

    const handleDeleteConversation = async () => {
        if (!deletingConv) return;
        const { id } = deletingConv;
        try {
            await deleteConversation(id);
            queryClient.setQueryData<Conversation[]>(
                ['chat-conversations', pdfId, undefined],
                (old = []) => old.filter((c) => c.id !== id),
            );
            if (activeConversationId === id) {
                setActiveConversationId(null);
                clearStreaming();
                setIndexError(null);
            }
        } catch {
            toast.error('Failed to delete conversation');
        } finally {
            setDeletingConv(null);
        }
    };

    // Combined message list: persisted history + in-flight streaming message.
    // Filter the streaming message's ID from history to prevent a duplicate when the
    // optimistic cache write and the still-live streamingMessage both exist briefly.
    const displayMessages = [
        ...history.filter(m => !streamingMessage || m.id !== streamingMessage.id),
        ...(streamingMessage ? [{
            id: streamingMessage.id,
            role: 'assistant' as const,
            content: streamingMessage.content,
            context_chunks: streamingMessage.isStreaming ? null : streamingMessage.context_chunks,
            isStreaming: streamingMessage.isStreaming,
        }] : []),
    ];

    const noConversation = !loadingConvs && conversations.length === 0;

    return (
        <div className="w-80 h-full border-l bg-background flex flex-col shrink-0">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-primary" />
                    <h2 className="font-semibold">Chat</h2>
                </div>
                <div className="flex items-center gap-1">
                    {activeConversationId && (
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                                const conv = conversations.find((c) => c.id === activeConversationId);
                                const idx = conversations.findIndex((c) => c.id === activeConversationId);
                                setDeletingConv({ id: activeConversationId, title: conv?.title || `Chat ${idx + 1}` });
                            }}
                            title="Delete conversation"
                        >
                            <Trash2 className="h-4 w-4" />
                        </Button>
                    )}
                    <Button variant="ghost" size="icon" onClick={handleNewConversation} title="New conversation">
                        <Plus className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Conversation picker (if multiple) */}
            {conversations.length > 1 && (
                <div className="px-3 py-2 border-b shrink-0">
                    <Select
                        value={activeConversationId ?? ''}
                        onValueChange={(id) => { setActiveConversationId(id); clearStreaming(); }}
                    >
                        <SelectTrigger className="h-7 text-xs">
                            <SelectValue placeholder="Select conversation" />
                        </SelectTrigger>
                        <SelectContent>
                            {conversations.map((conv, i) => (
                                <SelectItem key={conv.id} value={conv.id} className="text-xs">
                                    {conv.title || `Chat ${i + 1}`}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}

            {/* Empty state — no conversations yet */}
            {noConversation && (
                <div className="flex-1 flex flex-col items-center justify-center gap-3 p-6 text-center">
                    <BookOpen className="h-8 w-8 text-muted-foreground/50" />
                    <p className="text-sm text-muted-foreground">
                        Start a conversation to chat with this paper.
                    </p>
                    <Button size="sm" onClick={handleNewConversation} disabled={createConversation.isPending}>
                        {createConversation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                        New conversation
                    </Button>
                </div>
            )}

            {/* Indexing error banner */}
            {indexError && (
                <div className="mx-3 mt-2 flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive shrink-0">
                    <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                        <p className="font-medium">Indexing failed</p>
                        <p className="text-destructive/80 mt-0.5 break-words">{indexError}</p>
                    </div>
                    <button
                        onClick={handleRetry}
                        disabled={isSending}
                        className="flex items-center gap-1 text-xs font-medium text-destructive hover:text-destructive/80 disabled:opacity-50 shrink-0"
                        title="Retry indexing"
                    >
                        <RefreshCw className="h-3 w-3" />
                        Retry
                    </button>
                </div>
            )}

            {/* Message list */}
            {!noConversation && (
                <ScrollArea className="flex-1 px-3 py-2">
                    <ChatMessageList
                        messages={displayMessages}
                        isSending={isSending}
                        emptyMessage="Ask a question about this paper."
                        onChunkClick={(chunk) => setCurrentPage(chunk.page_number)}
                        onPageClick={(page) => setCurrentPage(page)}
                    />
                    <div ref={bottomRef} />
                </ScrollArea>
            )}

            <DeleteConversationDialog
                open={!!deletingConv}
                conversationTitle={deletingConv?.title ?? ''}
                isLoading={isDeletingConv}
                onConfirm={handleDeleteConversation}
                onCancel={() => setDeletingConv(null)}
            />

            {/* Input */}
            {!noConversation && (
                <div className="shrink-0 p-3 border-t flex gap-2 items-end">
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask about this paper… (Enter to send)"
                        className="resize-none text-sm min-h-[60px] max-h-[120px]"
                        disabled={isSending}
                    />
                    <Button
                        size="icon"
                        onClick={() => handleSend()}
                        disabled={!input.trim() || isSending || !activeConversationId}
                        className="shrink-0"
                    >
                        {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </Button>
                </div>
            )}
        </div>
    );
};
