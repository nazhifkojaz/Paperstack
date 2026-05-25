import { BookOpen, Loader2, Plus } from 'lucide-react';
import type { KeyboardEventHandler, RefObject } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChatMessageList, type ChatMessageProps } from '@/components/chat/ChatMessageList';
import type { ContextChunk } from '@/api/chat';
import { ChatIndexErrorBanner } from './ChatIndexErrorBanner';
import { ChatInput } from './ChatInput';

interface PdfChatPanelBodyProps {
  activeConversationId: string | null;
  bottomRef: RefObject<HTMLDivElement | null>;
  displayMessages: ChatMessageProps[];
  emptyConversationList: boolean;
  indexError: string | null;
  input: string;
  isCreatingConversation: boolean;
  isFullscreen: boolean;
  isSending: boolean;
  userAvatarUrl?: string;
  onChunkClick: (chunk: ContextChunk) => void;
  onDismissFailed: (messageId: string) => void;
  onInputKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
  onNewConversation: () => void;
  onPageClick: (page: number) => void;
  onRetry: () => void;
  onRetryFailed: (messageId: string) => void;
  onSend: () => void;
  onSetInput: (value: string) => void;
  onStop: () => void;
}

export function PdfChatPanelBody({
  activeConversationId,
  bottomRef,
  displayMessages,
  emptyConversationList,
  indexError,
  input,
  isCreatingConversation,
  isFullscreen,
  isSending,
  userAvatarUrl,
  onChunkClick,
  onDismissFailed,
  onInputKeyDown,
  onNewConversation,
  onPageClick,
  onRetry,
  onRetryFailed,
  onSend,
  onSetInput,
  onStop,
}: PdfChatPanelBodyProps) {
  if (emptyConversationList) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-6 text-center">
        <BookOpen className="h-8 w-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">
          Start a conversation to chat with this paper.
        </p>
        <Button size="sm" onClick={onNewConversation} disabled={isCreatingConversation}>
          {isCreatingConversation ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Plus className="h-4 w-4 mr-2" />
          )}
          New conversation
        </Button>
      </div>
    );
  }

  return (
    <>
      <ChatIndexErrorBanner
        error={indexError}
        isSending={isSending}
        onRetry={onRetry}
      />
      <ScrollArea className="flex-1 px-3 py-2">
        <div className={isFullscreen ? 'mx-auto max-w-2xl w-full' : ''}>
          <ChatMessageList
            messages={displayMessages}
            isSending={isSending}
            userAvatarUrl={userAvatarUrl}
            emptyMessage="Ask a question about this paper."
            onChunkClick={onChunkClick}
            onPageClick={onPageClick}
            onRetryFailed={onRetryFailed}
            onDismissFailed={onDismissFailed}
          />
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
      <ChatInput
        input={input}
        setInput={onSetInput}
        isSending={isSending}
        onSend={onSend}
        onStop={onStop}
        onKeyDown={onInputKeyDown}
        placeholder="Ask about this paper... (Enter to send)"
        disabled={!activeConversationId}
        wrapperClassName={isFullscreen ? 'flex justify-center' : ''}
        innerClassName={isFullscreen ? 'w-full max-w-2xl' : ''}
      />
    </>
  );
}
