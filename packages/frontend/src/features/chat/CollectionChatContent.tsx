import type { KeyboardEventHandler, RefObject } from 'react';
import { MessageSquare, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { ChatMessageList, type ChatMessageProps } from '@/components/chat/ChatMessageList';
import { BASE_URL } from '@/lib/config';
import { ChatInput } from './ChatInput';

interface CollectionChatContentProps {
  activeConversationId: string | null;
  bottomRef: RefObject<HTMLDivElement | null>;
  displayMessages: ChatMessageProps[];
  input: string;
  isCreatingConversation: boolean;
  isSending: boolean;
  userAvatarUrl?: string;
  onDismissFailed: (messageId: string) => void;
  onInputKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
  onNewConversation: () => void;
  onRetryFailed: (messageId: string) => void;
  onSend: () => void;
  onSetInput: (value: string) => void;
  onStop: () => void;
}

export function CollectionChatContent({
  activeConversationId,
  bottomRef,
  displayMessages,
  input,
  isCreatingConversation,
  isSending,
  userAvatarUrl,
  onDismissFailed,
  onInputKeyDown,
  onNewConversation,
  onRetryFailed,
  onSend,
  onSetInput,
  onStop,
}: CollectionChatContentProps) {
  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="p-4 border-b flex items-center gap-2 shrink-0">
        <MessageSquare className="h-4 w-4 text-primary" />
        <h1 className="font-semibold">Chat with collection</h1>
      </div>
      {!activeConversationId ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-8">
          <MessageSquare className="h-10 w-10 text-muted-foreground/30" />
          <p className="text-muted-foreground">
            Select or create a conversation to get started.
          </p>
          <Button onClick={onNewConversation} disabled={isCreatingConversation}>
            <Plus className="h-4 w-4 mr-2" />
            New conversation
          </Button>
        </div>
      ) : (
        <>
          <ScrollArea className="flex-1 px-4 py-3">
            <ChatMessageList
              messages={displayMessages}
              isSending={isSending}
              userAvatarUrl={userAvatarUrl}
              emptyMessage="Ask a question about the papers in this collection."
              onChunkClickUrl={(chunk) => {
                if (chunk.pdf_id) {
                  window.open(`${BASE_URL}/viewer/${chunk.pdf_id}`, '_blank');
                }
              }}
              onRetryFailed={onRetryFailed}
              onDismissFailed={onDismissFailed}
            />
            <div ref={bottomRef} />
          </ScrollArea>
          <Separator />
          <ChatInput
            input={input}
            setInput={onSetInput}
            isSending={isSending}
            onSend={onSend}
            onStop={onStop}
            onKeyDown={onInputKeyDown}
            placeholder="Ask about papers in this collection... (Enter to send)"
            textareaClassName="min-h-[72px] max-h-[160px]"
            buttonClassName="h-10 w-10"
            wrapperClassName="border-t-0"
            innerClassName="p-4 gap-3"
          />
        </>
      )}
    </div>
  );
}
