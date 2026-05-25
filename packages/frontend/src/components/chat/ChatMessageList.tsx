/**
 * Shared message list component for chat interfaces.
 * Renders user/assistant messages with markdown and context chunk badges.
 *
 * @example
 * <ChatMessageList
 *     messages={displayMessages}
 *     onChunkClick={(chunk) => jumpToPage(chunk.page_number)}
 *     onChunkClickUrl={(chunk) => window.open(`/viewer/${chunk.pdf_id}`, '_blank')}
 * />
 */

import { useMemo, useState } from 'react';
import { Loader2, User, Bot, Copy, Check, RefreshCw, X, AlertCircle } from 'lucide-react';
import Markdown, { defaultUrlTransform } from 'react-markdown';
import { Badge } from '@/components/ui/badge';
import { HoverCard, HoverCardTrigger, HoverCardContent } from '@/components/ui/hover-card';
import { type ContextChunk } from '@/api/chat';
import { useCitation } from '@/api/citations';
import { CitationPreview } from './CitationPreview';
import { InlineCitationLink } from './InlineCitationLink';
import { createPageRefPlugin } from '@/lib/remarkPageRefs';
import { createInlineCitationPlugin } from '@/lib/remarkInlineCitations';

export interface ChatMessageProps {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    context_chunks: ContextChunk[] | null;
    isStreaming?: boolean;
    error?: string | null;
    created_at?: string;
}

interface ChatMessageListProps {
    messages: ChatMessageProps[];
    emptyMessage?: string;
    isSending?: boolean;
    userAvatarUrl?: string;
    onChunkClick?: (chunk: ContextChunk) => void;
    onChunkClickUrl?: (chunk: ContextChunk) => void;
    onPageClick?: (page: number) => void;
    onRetryFailed?: (messageId: string) => void;
    onDismissFailed?: (messageId: string) => void;
}

/**
 * Renders a list of chat messages with proper styling and interactions.
 */
export function ChatMessageList({
    messages,
    emptyMessage = 'Ask a question to get started.',
    isSending = false,
    userAvatarUrl,
    onChunkClick,
    onChunkClickUrl,
    onPageClick,
    onRetryFailed,
    onDismissFailed,
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
                    userAvatarUrl={userAvatarUrl}
                    onChunkClick={onChunkClick}
                    onChunkClickUrl={onChunkClickUrl}
                    onPageClick={onPageClick}
                    onRetryFailed={onRetryFailed}
                    onDismissFailed={onDismissFailed}
                />
            ))}
        </div>
    );
}

interface MessageBubbleProps {
    message: ChatMessageProps;
    userAvatarUrl?: string;
    onChunkClick?: (chunk: ContextChunk) => void;
    onChunkClickUrl?: (chunk: ContextChunk) => void;
    onPageClick?: (page: number) => void;
    onRetryFailed?: (messageId: string) => void;
    onDismissFailed?: (messageId: string) => void;
}

function formatTime(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function MessageBubble({ message, userAvatarUrl, onChunkClick, onChunkClickUrl, onPageClick, onRetryFailed, onDismissFailed }: MessageBubbleProps) {
    const isUser = message.role === 'user';
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(message.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // ignore
        }
    };

    const remarkPlugins = useMemo(
        () => onPageClick ? [createPageRefPlugin(), createInlineCitationPlugin()] : [createInlineCitationPlugin()],
        [onPageClick]
    );

    const markdownComponents = useMemo(() => {
        return {
            a: ({ href, children, ...props }: React.ComponentPropsWithoutRef<'a'>) => {
                if (href?.startsWith('page://')) {
                    const page = parseInt(href.slice(7), 10);
                    if (!isNaN(page) && onPageClick) {
                        return (
                            <button
                                className="inline text-primary underline underline-offset-2
                                           hover:opacity-80 cursor-pointer bg-transparent
                                           border-none p-0 font-inherit text-inherit"
                                onClick={() => onPageClick(page)}
                            >
                                {children}
                            </button>
                        );
                    }
                }
                if (href?.startsWith('citation://') && message.context_chunks && message.context_chunks.length > 0) {
                    return (
                        <InlineCitationLink
                            href={href}
                            contextChunks={message.context_chunks}
                            onChunkClick={onChunkClick}
                            onChunkClickUrl={onChunkClickUrl}
                        >
                            {children}
                        </InlineCitationLink>
                    );
                }
                return <a href={href} {...props}>{children}</a>;
            },
        };
    }, [onPageClick, message.context_chunks, onChunkClick, onChunkClickUrl]);

    const urlTransform = useMemo(
        () => (url: string) => url.startsWith('page://') || url.startsWith('citation://') ? url : defaultUrlTransform(url),
        []
    );

    return (
        <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
            {/* Avatar */}
            <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 overflow-hidden ${isUser ? 'bg-primary/10' : 'bg-muted'}`}>
                {isUser && userAvatarUrl ? (
                    <img
                        src={userAvatarUrl}
                        alt="User avatar"
                        className="w-full h-full object-cover"
                    />
                ) : isUser ? (
                    <User className="h-3.5 w-3.5 text-primary" />
                ) : (
                    <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                )}
            </div>

            <div className={`flex flex-col gap-0.5 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
                <div
                    className={`rounded-xl px-3.5 py-2.5 text-sm break-words relative group ${
                        isUser
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-foreground'
                    }`}
                >
                    {message.error
                        ? (
                            <div className="flex flex-col gap-2">
                                <div className="flex items-start gap-2">
                                    <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
                                    <div className="flex-1 min-w-0">
                                        <p className="font-medium text-xs text-destructive">Failed to generate response</p>
                                        <p className="text-xs text-destructive/80 mt-1 break-words">{message.error}</p>
                                    </div>
                                </div>
                                <div className="flex gap-1 justify-end">
                                    <button
                                        onClick={() => onRetryFailed?.(message.id)}
                                        className="flex items-center gap-1 text-xs font-medium text-destructive hover:text-destructive/80 transition-colors cursor-pointer"
                                    >
                                        <RefreshCw className="h-3 w-3" />
                                        Retry
                                    </button>
                                    <button
                                        onClick={() => onDismissFailed?.(message.id)}
                                        className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                    >
                                        <X className="h-3 w-3" />
                                        Dismiss
                                    </button>
                                </div>
                            </div>
                        )
                        : !message.content && message.isStreaming
                            ? (
                                <div className="flex items-center gap-2 text-muted-foreground min-w-[80px]">
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    <span className="text-xs">Thinking…</span>
                                </div>
                            )
                            : isUser
                                ? <span className="whitespace-pre-wrap">{message.content}</span>
                                : (
                                    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
                                        <Markdown
                                            remarkPlugins={remarkPlugins}
                                            components={markdownComponents}
                                            urlTransform={urlTransform}
                                        >
                                            {message.content}
                                        </Markdown>
                                    </div>
                                )
                    }
                    {message.isStreaming && message.content && (
                        <span className="inline-block w-1.5 h-3.5 bg-current ml-0.5 animate-pulse align-middle" />
                    )}

                    {/* Copy button for assistant messages */}
                    {!isUser && message.content && !message.isStreaming && !message.error && (
                        <button
                            onClick={handleCopy}
                            className="absolute -top-2 -right-2 p-1 rounded-md bg-background border shadow-sm opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                            title="Copy to clipboard"
                        >
                            {copied ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
                        </button>
                    )}
                </div>

                {/* Timestamp */}
                {message.created_at && (
                    <span className="text-[10px] text-muted-foreground px-1">
                        {formatTime(message.created_at)}
                    </span>
                )}

                {/* Context chunk badges */}
                {!isUser && message.context_chunks && message.context_chunks.length > 0 && (
                    <div className="flex flex-wrap gap-1 max-w-full">
                        {message.context_chunks.map((chunk) => (
                            <ContextChunkBadge
                                key={chunk.chunk_id}
                                chunk={chunk}
                                onChunkClick={onChunkClick}
                                onChunkClickUrl={onChunkClickUrl}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function ContextChunkBadge({
    chunk,
    onChunkClick,
    onChunkClickUrl,
}: {
    chunk: ContextChunk;
    onChunkClick?: (chunk: ContextChunk) => void;
    onChunkClickUrl?: (chunk: ContextChunk) => void;
}) {
    const { data: citation, isLoading } = useCitation(chunk.pdf_id || '');

    const hasPdfInfo = !!chunk.pdf_id && !!chunk.pdf_title;
    const startPage = chunk.page_number;
    const endPage = chunk.end_page_number;
    const pageLabel = endPage && endPage > startPage
        ? `p.${startPage}-${endPage}`
        : `p.${startPage}`;
    const label = hasPdfInfo
        ? `${chunk.pdf_title!.length > 18 ? chunk.pdf_title!.slice(0, 18) + '…' : chunk.pdf_title} · ${pageLabel}`
        : pageLabel;

    const handleClick = () => {
        if (onChunkClickUrl && hasPdfInfo) {
            onChunkClickUrl(chunk);
        } else if (onChunkClick) {
            onChunkClick(chunk);
        }
    };

    const isClickable = onChunkClick || (onChunkClickUrl && hasPdfInfo);

    return (
        <HoverCard openDelay={200} closeDelay={150}>
            <HoverCardTrigger asChild>
                <Badge
                    variant="outline"
                    className={`text-xs ${isClickable ? 'cursor-pointer hover:bg-primary/10 transition-colors' : ''}`}
                    onClick={isClickable ? handleClick : undefined}
                >
                    {label}
                </Badge>
            </HoverCardTrigger>
            <HoverCardContent side="top" align="center" className="p-0">
                {isLoading ? (
                    <div className="w-80 h-24 flex items-center justify-center">
                        <span className="text-xs text-muted-foreground animate-pulse">Loading...</span>
                    </div>
                ) : (
                    <CitationPreview
                        citation={citation ?? null}
                        chunk={chunk}
                        onNavigate={isClickable ? handleClick : undefined}
                    />
                )}
            </HoverCardContent>
        </HoverCard>
    );
}
