import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useChatHistory } from '@/api/chat';
import { useChatStream } from '@/hooks/useChatStream';
import { useAuthStore } from '@/stores/authStore';
import { CollectionChatContent } from './CollectionChatContent';
import { CollectionChatSidebar } from './CollectionChatSidebar';
import { DeleteConversationDialog } from './DeleteConversationDialog';
import { useChatMessages } from './useChatMessages';
import { useConversationManager } from './useConversationManager';

export function CollectionChatPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const navigate = useNavigate();
  const userAvatarUrl = useAuthStore((state) => state.user?.avatar_url);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const { data: history = [] } = useChatHistory(activeConversationId);
  const {
    bottomRef,
    clearStreaming,
    handleDismissFailed,
    handleKeyDown,
    handleRetryFailed,
    handleSend,
    handleStop,
    input,
    isSending,
    setInput,
    streamingMessage,
  } = useChatStream({
    conversationId: activeConversationId,
    invalidateQueryKeys: [['chat-history', activeConversationId]],
    onError: (error) => toast.error(error),
  });
  const {
    cancelDeleteConversation,
    confirmDeleteConversation,
    conversations,
    createNewConversation,
    deletingConversation,
    isCreatingConversation,
    isDeletingConversation,
    isLoadingConversations,
    requestDeleteConversation,
    selectConversation,
  } = useConversationManager({
    collectionId,
    activeConversationId,
    setActiveConversationId,
    clearStreaming,
  });
  const displayMessages = useChatMessages(history, streamingMessage);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <CollectionChatSidebar
        activeConversationId={activeConversationId}
        conversations={conversations}
        isCreatingConversation={isCreatingConversation}
        isLoadingConversations={isLoadingConversations}
        onBack={() => navigate('/library')}
        onDeleteConversation={requestDeleteConversation}
        onNewConversation={createNewConversation}
        onSelectConversation={selectConversation}
      />
      <CollectionChatContent
        activeConversationId={activeConversationId}
        bottomRef={bottomRef}
        displayMessages={displayMessages}
        input={input}
        isCreatingConversation={isCreatingConversation}
        isSending={isSending}
        userAvatarUrl={userAvatarUrl}
        onDismissFailed={handleDismissFailed}
        onInputKeyDown={handleKeyDown}
        onNewConversation={createNewConversation}
        onRetryFailed={handleRetryFailed}
        onSend={() => handleSend()}
        onSetInput={setInput}
        onStop={handleStop}
      />
      <DeleteConversationDialog
        open={!!deletingConversation}
        conversationTitle={deletingConversation?.title ?? ''}
        isLoading={isDeletingConversation}
        onConfirm={confirmDeleteConversation}
        onCancel={cancelDeleteConversation}
      />
    </div>
  );
}
