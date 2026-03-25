/**
 * Shared message list component for chat interfaces.
 * Renders user/assistant messages with markdown and context chunk badges.
 *
 * @example
 * <ChatMessageList
 *     messages={displayMessages}
 *     onChunkClick={(chunk) => setCurrentPage(chunk.page_number)}
 *     onChunkClickUrl={(chunk) => window.open(`/viewer/${chunk.pdf_id}`, '_blank')}
 * />
 */

import { Loader2 } from 'lucide-react';
import Markdown from 'react-markdown';
import { Badge } from '@/components/ui/badge';
import { type ContextChunk } from '@/api/chat';

export interface ChatMessageProps {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    context_chunks: ContextChunk[] | null;
    isStreaming?: boolean;
}

export interface ChatMessageListProps {
    messages: ChatMessageProps[];
    emptyMessage?: string;
    isSending?: boolean;
    onChunkClick?: (chunk: ContextChunk) => void;
    onChunkClickUrl?: (chunk: ContextChunk) => void;
}

/**
 * Renders a list of chat messages with proper styling and interactions.
 */
export function ChatMessageList({
    messages,
    emptyMessage = 'Ask a question to get started.',
    isSending = false,
    onChunkClick,
    onChunkClickUrl,
}: ChatMessageListProps) {
    if (messages.length === 0 && !isSending) {
        return (
            <p className="text-xs text-muted-foreground text-center mt-8">
                {emptyMessage}
            </p>
        );
    }

    return (
        <div className="flex flex-col gap-3">
            {messages.map((msg) => (
                <MessageBubble
                    key={msg.id}
                    message={msg}
                    onChunkClick={onChunkClick}
                    onChunkClickUrl={onChunkClickUrl}
                />
            ))}
        </div>
    );
}

interface MessageBubbleProps {
    message: ChatMessageProps;
    onChunkClick?: (chunk: ContextChunk) => void;
    onChunkClickUrl?: (chunk: ContextChunk) => void;
}

function MessageBubble({ message, onChunkClick, onChunkClickUrl }: MessageBubbleProps) {
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
                        : (
                            <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
                                <Markdown>{message.content}</Markdown>
                            </div>
                        )
                }
                {message.isStreaming && message.content && (
                    <span className="inline-block w-1 h-3 bg-current ml-0.5 animate-pulse" />
                )}
            </div>

            {/* Context chunk badges */}
            {!isUser && message.context_chunks && message.context_chunks.length > 0 && (
                <div className="flex flex-wrap gap-1 max-w-[90%]">
                    {message.context_chunks.map((chunk) => {
                        // Determine label and click behavior based on available data
                        const hasPdfInfo = !!chunk.pdf_id && !!chunk.pdf_title;
                        const label = hasPdfInfo
                            ? `${chunk.pdf_title.length > 18 ? chunk.pdf_title.slice(0, 18) + '…' : chunk.pdf_title} · p.${chunk.page_number}`
                            : `p.${chunk.page_number}`;

                        const handleClick = () => {
                            if (onChunkClickUrl && hasPdfInfo) {
                                onChunkClickUrl(chunk);
                            } else if (onChunkClick) {
                                onChunkClick(chunk);
                            }
                        };

                        const isClickable = onChunkClick || (onChunkClickUrl && hasPdfInfo);

                        return (
                            <Badge
                                key={chunk.chunk_id}
                                variant="outline"
                                className={`text-xs ${isClickable ? 'cursor-pointer hover:bg-primary/10 transition-colors' : ''}`}
                                onClick={isClickable ? handleClick : undefined}
                                title={chunk.snippet}
                            >
                                {label}
                            </Badge>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
