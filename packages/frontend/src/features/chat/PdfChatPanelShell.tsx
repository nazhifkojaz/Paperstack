import type { KeyboardEventHandler, RefObject } from 'react';
import type { ChatMessageProps } from '@/components/chat/ChatMessageList';
import type { ContextChunk, Conversation } from '@/api/chat';
import { ChatConversationSelect } from './ChatConversationSelect';
import { DeleteConversationDialog } from './DeleteConversationDialog';
import { PdfChatPanelBody } from './PdfChatPanelBody';
import { PdfChatPanelHeader } from './PdfChatPanelHeader';
import { ChatIntroBanner } from '@/features/onboarding/ChatIntroBanner';

export interface PdfChatPanelShellProps {
  activeConversationId: string | null;
  bottomRef: RefObject<HTMLDivElement | null>;
  conversations: Conversation[];
  deletingConversation: { id: string; title: string } | null;
  displayMessages: ChatMessageProps[];
  emptyConversationList: boolean;
  indexError: string | null;
  input: string;
  isCreatingConversation: boolean;
  isDeletingConversation: boolean;
  isFullscreen: boolean;
  isSending: boolean;
  userAvatarUrl?: string;
  onCancelDeleteConversation: () => void;
  onChunkClick: (chunk: ContextChunk) => void;
  onClose: () => void;
  onConfirmDeleteConversation: () => void;
  onDeleteConversation: (conversationId: string, title: string) => void;
  onDismissFailed: (messageId: string) => void;
  onInputKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
  onNewConversation: () => void;
  onPageClick: (page: number) => void;
  onRetry: () => void;
  onRetryFailed: (messageId: string) => void;
  onSelectConversation: (conversationId: string) => void;
  onSend: () => void;
  onSetInput: (value: string) => void;
  onStop: () => void;
  onToggleFullscreen: () => void;
}

export function PdfChatPanelShell({
  activeConversationId,
  bottomRef,
  conversations,
  deletingConversation,
  displayMessages,
  emptyConversationList,
  indexError,
  input,
  isCreatingConversation,
  isDeletingConversation,
  isFullscreen,
  isSending,
  userAvatarUrl,
  onCancelDeleteConversation,
  onChunkClick,
  onClose,
  onConfirmDeleteConversation,
  onDeleteConversation,
  onDismissFailed,
  onInputKeyDown,
  onNewConversation,
  onPageClick,
  onRetry,
  onRetryFailed,
  onSelectConversation,
  onSend,
  onSetInput,
  onStop,
  onToggleFullscreen,
}: PdfChatPanelShellProps) {
  return (
    <div className={`fixed inset-0 z-50 flex ${isFullscreen ? 'items-center justify-center' : 'justify-end'}`}>
      {!isFullscreen && (
        <div
          className="absolute inset-0 bg-black/20 backdrop-blur-[2px] backdrop-enter"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <div className={`relative h-full bg-background shadow-2xl drawer-enter flex flex-col ${isFullscreen ? 'w-full border-0' : 'w-full max-w-[400px] border-l'}`}>
        <PdfChatPanelHeader
          activeConversationId={activeConversationId}
          conversations={conversations}
          isFullscreen={isFullscreen}
          onClose={onClose}
          onDeleteConversation={onDeleteConversation}
          onNewConversation={onNewConversation}
          onToggleFullscreen={onToggleFullscreen}
        />
        <ChatIntroBanner />
        <ChatConversationSelect
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelect={onSelectConversation}
        />
        <PdfChatPanelBody
          activeConversationId={activeConversationId}
          bottomRef={bottomRef}
          displayMessages={displayMessages}
          emptyConversationList={emptyConversationList}
          indexError={indexError}
          input={input}
          isCreatingConversation={isCreatingConversation}
          isFullscreen={isFullscreen}
          isSending={isSending}
          userAvatarUrl={userAvatarUrl}
          onChunkClick={onChunkClick}
          onDismissFailed={onDismissFailed}
          onInputKeyDown={onInputKeyDown}
          onNewConversation={onNewConversation}
          onPageClick={onPageClick}
          onRetry={onRetry}
          onRetryFailed={onRetryFailed}
          onSend={onSend}
          onSetInput={onSetInput}
          onStop={onStop}
        />
        <DeleteConversationDialog
          open={!!deletingConversation}
          conversationTitle={deletingConversation?.title ?? ''}
          isLoading={isDeletingConversation}
          onConfirm={onConfirmDeleteConversation}
          onCancel={onCancelDeleteConversation}
        />
      </div>
    </div>
  );
}
