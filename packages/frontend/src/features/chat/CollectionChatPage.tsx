import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { useParams, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Plus, Send, Loader2, Trash2, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';

import {
    useConversations,
    useCreateConversation,
    useChatHistory,
    useDeleteConversation,
    streamChat,
    type ContextChunk,
} from '@/api/chat';
import { DeleteConversationDialog } from './DeleteConversationDialog';

export function CollectionChatPage() {
    const { collectionId } = useParams<{ collectionId: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();

    const [activeConvId, setActiveConvId] = useState<string | null>(null);
    const [deletingConv, setDeletingConv] = useState<{ id: string; title: string } | null>(null);
    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [streamContent, setStreamContent] = useState('');
    const [streamChunks, setStreamChunks] = useState<ContextChunk[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);

    const { data: conversations = [], isLoading: loadingConvs } = useConversations(undefined, collectionId);
    const createConversation = useCreateConversation();
    const deleteConversation = useDeleteConversation();
    const { data: history = [] } = useChatHistory(activeConvId);

    // Auto-select first conversation
    useEffect(() => {
        if (!loadingConvs && conversations.length > 0 && !activeConvId) {
            setActiveConvId(conversations[0].id);
        }
    }, [conversations, loadingConvs, activeConvId]);

    // Scroll to bottom
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [history, streamContent]);

    const handleNewConversation = async () => {
        if (!collectionId) return;
        try {
            const conv = await createConversation.mutateAsync({ collection_id: collectionId });
            setActiveConvId(conv.id);
            setStreamContent('');
            setStreamChunks([]);
        } catch {
            toast.error('Failed to create conversation');
        }
    };

    const handleDeleteConversation = async () => {
        if (!deletingConv) return;
        const { id } = deletingConv;
        try {
            await deleteConversation.mutateAsync(id);
            queryClient.setQueryData<typeof conversations>(
                ['chat-conversations', undefined, collectionId],
                (old = []) => old.filter((c) => c.id !== id),
            );
            if (activeConvId === id) {
                setActiveConvId(null);
                setStreamContent('');
                setStreamChunks([]);
            }
        } catch {
            toast.error('Failed to delete conversation');
        } finally {
            setDeletingConv(null);
        }
    };

    const handleSend = async () => {
        const message = input.trim();
        if (!message || isSending || !activeConvId) return;

        setInput('');
        setIsSending(true);
        setIsStreaming(true);
        setStreamContent('');
        setStreamChunks([]);

        try {
            await streamChat({
                conversationId: activeConvId,
                message,
                onToken: (token) => setStreamContent((s) => s + token),
                onDone: (_messageId, chunks) => {
                    setIsStreaming(false);
                    setStreamChunks(chunks);
                    queryClient.invalidateQueries({ queryKey: ['chat-history', activeConvId] });
                    setTimeout(() => { setStreamContent(''); setStreamChunks([]); }, 100);
                },
                onError: (err) => {
                    setIsStreaming(false);
                    setStreamContent('');
                    toast.error(err.message);
                },
            });
        } finally {
            setIsSending(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const allMessages = [
        ...history,
        ...(isStreaming || streamContent ? [{
            id: 'streaming',
            role: 'assistant' as const,
            content: streamContent,
            context_chunks: streamChunks.length > 0 ? streamChunks : null,
            created_at: new Date().toISOString(),
            isStreaming,
        }] : []),
    ];

    return (
        <div className="flex h-screen overflow-hidden bg-background">
            {/* Sidebar */}
            <div className="w-64 border-r flex flex-col shrink-0">
                <div className="p-4 border-b flex items-center gap-2">
                    <Button variant="ghost" size="icon" onClick={() => navigate('/library')} title="Back to library">
                        <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <h2 className="font-semibold text-sm truncate flex-1">Collection Chat</h2>
                </div>

                <div className="p-2 border-b">
                    <Button
                        variant="outline"
                        size="sm"
                        className="w-full gap-2"
                        onClick={handleNewConversation}
                        disabled={createConversation.isPending}
                    >
                        <Plus className="h-4 w-4" />
                        New conversation
                    </Button>
                </div>

                <ScrollArea className="flex-1">
                    {loadingConvs ? (
                        <div className="flex justify-center p-4">
                            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        </div>
                    ) : conversations.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center p-4">
                            No conversations yet.
                        </p>
                    ) : (
                        <div className="p-2 flex flex-col gap-1 overflow-hidden">
                            {conversations.map((conv, i) => {
                                const title = conv.title || `Chat ${i + 1}`;
                                const displayTitle = title.length > 28 ? `${title.slice(0, 28)}…` : title;
                                return (
                                <div
                                    key={conv.id}
                                    className={`w-full flex items-center gap-1 rounded-md px-2 py-1.5 cursor-pointer transition-colors ${
                                        conv.id === activeConvId
                                            ? 'bg-primary/10 text-primary'
                                            : 'hover:bg-muted text-muted-foreground'
                                    }`}
                                    onClick={() => { setActiveConvId(conv.id); setStreamContent(''); setStreamChunks([]); }}
                                >
                                    <span className="text-xs flex-1 min-w-0" title={title}>
                                        {displayTitle}
                                    </span>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-5 w-5 shrink-0 text-muted-foreground hover:text-destructive"
                                        onClick={(e) => { e.stopPropagation(); setDeletingConv({ id: conv.id, title }); }}
                                    >
                                        <Trash2 className="h-3 w-3" />
                                    </Button>
                                </div>
                                );
                            })}
                        </div>
                    )}
                </ScrollArea>
            </div>

            {/* Chat area */}
            <div className="flex flex-col flex-1 overflow-hidden">
                {/* Header */}
                <div className="p-4 border-b flex items-center gap-2 shrink-0">
                    <MessageSquare className="h-4 w-4 text-primary" />
                    <h1 className="font-semibold">Chat with collection</h1>
                </div>

                {!activeConvId ? (
                    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-8">
                        <MessageSquare className="h-10 w-10 text-muted-foreground/30" />
                        <p className="text-muted-foreground">Select or create a conversation to get started.</p>
                        <Button onClick={handleNewConversation} disabled={createConversation.isPending}>
                            <Plus className="h-4 w-4 mr-2" />
                            New conversation
                        </Button>
                    </div>
                ) : (
                    <>
                        <ScrollArea className="flex-1 px-4 py-3">
                            {allMessages.length === 0 && (
                                <p className="text-sm text-muted-foreground text-center mt-12">
                                    Ask a question about the papers in this collection.
                                </p>
                            )}
                            <div className="flex flex-col gap-4 max-w-3xl mx-auto">
                                {allMessages.map((msg) => (
                                    <div key={msg.id} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                                        <div className={`rounded-lg px-4 py-2.5 text-sm max-w-[80%] break-words ${
                                            msg.role === 'user'
                                                ? 'bg-primary text-primary-foreground'
                                                : 'bg-muted text-foreground'
                                        }`}>
                                            {!msg.content && ('isStreaming' in msg && msg.isStreaming)
                                                ? <Loader2 className="h-3 w-3 animate-spin" />
                                                : msg.role === 'user'
                                                    ? <span className="whitespace-pre-wrap">{msg.content}</span>
                                                    : <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0"><Markdown>{msg.content}</Markdown></div>
                                            }
                                            {('isStreaming' in msg && msg.isStreaming) && msg.content && (
                                                <span className="inline-block w-1 h-3 bg-current ml-0.5 animate-pulse" />
                                            )}
                                        </div>
                                        {msg.role === 'assistant' && msg.context_chunks && msg.context_chunks.length > 0 && (
                                            <div className="flex flex-wrap gap-1 max-w-[80%]">
                                                {msg.context_chunks.map((chunk) => {
                                                    const title = chunk.pdf_title;
                                                    const label = title
                                                        ? `${title.length > 18 ? title.slice(0, 18) + '…' : title} · p.${chunk.page_number}`
                                                        : `p.${chunk.page_number}`;
                                                    return (
                                                        <Badge
                                                            key={chunk.chunk_id}
                                                            variant="outline"
                                                            className={`text-xs ${chunk.pdf_id ? 'cursor-pointer hover:bg-primary/10 transition-colors' : ''}`}
                                                            title={chunk.snippet}
                                                            onClick={() => {
                                                                if (chunk.pdf_id) {
                                                                    window.open(`${import.meta.env.BASE_URL}viewer/${chunk.pdf_id}`, '_blank');
                                                                }
                                                            }}
                                                        >
                                                            {label}
                                                        </Badge>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                            <div ref={bottomRef} />
                        </ScrollArea>

                        <Separator />

                        <div className="p-4 flex gap-3 items-end shrink-0">
                            <Textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Ask about papers in this collection… (Enter to send)"
                                className="resize-none text-sm min-h-[72px] max-h-[160px]"
                                disabled={isSending}
                            />
                            <Button
                                size="icon"
                                onClick={handleSend}
                                disabled={!input.trim() || isSending}
                                className="shrink-0 h-10 w-10"
                            >
                                {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                            </Button>
                        </div>
                    </>
                )}
            </div>
        <DeleteConversationDialog
            open={!!deletingConv}
            conversationTitle={deletingConv?.title ?? ''}
            isLoading={deleteConversation.isPending}
            onConfirm={handleDeleteConversation}
            onCancel={() => setDeletingConv(null)}
        />
        </div>
    );
}
