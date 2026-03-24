import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Plus, Send, Loader2, BookOpen, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

import { useChatStore } from '@/stores/chatStore';
import { usePdfViewerStore } from '@/stores/pdfViewerStore';
import {
    useConversations,
    useCreateConversation,
    useDeleteConversation,
    useChatHistory,
    streamChat,
    type ChatMessage,
    type Conversation,
    type ContextChunk,
} from '@/api/chat';
import { DeleteConversationDialog } from './DeleteConversationDialog';

interface ChatPanelProps {
    pdfId: string;
}

export const ChatPanel = ({ pdfId }: ChatPanelProps) => {
    const { isPanelOpen, activeConversationId, setActiveConversationId, streamingMessage,
        startStreaming, appendToken, finalizeStreaming, clearStreaming } = useChatStore();
    const { setCurrentPage } = usePdfViewerStore();
    const queryClient = useQueryClient();

    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [indexError, setIndexError] = useState<string | null>(null);
    const [lastMessage, setLastMessage] = useState<string>('');
    const [deletingConv, setDeletingConv] = useState<{ id: string; title: string } | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    const { data: conversations = [], isLoading: loadingConvs } = useConversations(pdfId);
    const createConversation = useCreateConversation();
    const { mutateAsync: deleteConversation, isPending: isDeletingConv } = useDeleteConversation();
    const { data: history = [] } = useChatHistory(activeConversationId);

    // Auto-select first conversation or create one
    useEffect(() => {
        if (loadingConvs || !isPanelOpen) return;
        if (conversations.length > 0 && !activeConversationId) {
            setActiveConversationId(conversations[0].id);
        }
    }, [conversations, loadingConvs, activeConversationId, isPanelOpen, setActiveConversationId]);

    // Scroll to bottom on new messages
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [history, streamingMessage?.content]);

    if (!isPanelOpen) return null;

    const handleNewConversation = async () => {
        try {
            const conv = await createConversation.mutateAsync({ pdf_id: pdfId });
            // Immediately add to cache so the message area appears without waiting for the refetch
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

    const handleSend = async (overrideMessage?: string) => {
        const message = (overrideMessage ?? input).trim();
        if (!message || isSending || !activeConversationId) return;

        setInput('');
        setIndexError(null);
        setLastMessage(message);
        setIsSending(true);
        const tempId = `temp-${Date.now()}`;
        startStreaming(tempId);

        try {
            await streamChat({
                conversationId: activeConversationId,
                message,
                onToken: (token) => appendToken(token),
                onDone: (messageId, chunks) => {
                    finalizeStreaming(messageId, chunks);
                },
                onError: (err) => {
                    clearStreaming();
                    if (err.message.includes('quota')) {
                        toast.error('Chat quota exhausted. Add an API key in Settings.');
                    } else if (err.message.toLowerCase().includes('index')) {
                        setIndexError(err.message);
                    } else {
                        toast.error(err.message);
                    }
                },
            });
            // Stream is fully done — refetch history first, then clear the streaming
            // message so it's never removed before the new history data arrives.
            await queryClient.invalidateQueries({ queryKey: ['chat-history', activeConversationId] });
            queryClient.invalidateQueries({ queryKey: ['chat-conversations', pdfId, undefined] });
            clearStreaming();
        } finally {
            setIsSending(false);
        }
    };

    const handleRetry = () => {
        if (lastMessage) handleSend(lastMessage);
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

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // Combined message list: persisted history + in-flight streaming message
    const displayMessages: Array<ChatMessage | { id: string; role: 'user' | 'assistant'; content: string; context_chunks: ContextChunk[] | null; isStreaming?: boolean }> = [
        ...history,
        ...(streamingMessage ? [{
            id: streamingMessage.id,
            role: 'assistant' as const,
            content: streamingMessage.content,
            context_chunks: streamingMessage.isStreaming ? null : streamingMessage.contextChunks,
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
                    {displayMessages.length === 0 && !isSending && (
                        <p className="text-xs text-muted-foreground text-center mt-8">
                            Ask a question about this paper.
                        </p>
                    )}

                    <div className="flex flex-col gap-3">
                        {displayMessages.map((msg) => (
                            <MessageBubble
                                key={msg.id}
                                message={msg}
                                onChunkClick={setCurrentPage}
                            />
                        ))}

                    </div>
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

// ── Sub-components ────────────────────────────────────────────────────────────

interface MessageBubbleProps {
    message: {
        id: string;
        role: 'user' | 'assistant';
        content: string;
        context_chunks: ContextChunk[] | null;
        isStreaming?: boolean;
    };
    onChunkClick: (page: number) => void;
}

const MessageBubble = ({ message, onChunkClick }: MessageBubbleProps) => {
    const isUser = message.role === 'user';

    return (
        <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
            <div
                className={`rounded-lg px-3 py-2 text-sm max-w-[90%] break-words ${
                    isUser
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-foreground'
                }`}
            >
                {!message.content && message.isStreaming
                    ? <Loader2 className="h-3 w-3 animate-spin" />
                    : isUser
                        ? <span className="whitespace-pre-wrap">{message.content}</span>
                        : <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0"><Markdown>{message.content}</Markdown></div>
                }
                {message.isStreaming && message.content && (
                    <span className="inline-block w-1 h-3 bg-current ml-0.5 animate-pulse" />
                )}
            </div>

            {/* Context chunk badges */}
            {!isUser && message.context_chunks && message.context_chunks.length > 0 && (
                <div className="flex flex-wrap gap-1 max-w-[90%]">
                    {message.context_chunks.map((chunk) => (
                        <Badge
                            key={chunk.chunk_id}
                            variant="outline"
                            className="text-xs cursor-pointer hover:bg-primary/10 transition-colors"
                            onClick={() => onChunkClick(chunk.page_number)}
                            title={chunk.snippet}
                        >
                            p.{chunk.page_number}
                        </Badge>
                    ))}
                </div>
            )}
        </div>
    );
};
