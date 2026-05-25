import { useAuthStore } from '@/stores/authStore';
import { useChatHighlightStore } from '@/stores/chatHighlightStore';
import { useChatStore } from '@/stores/chatStore';
import { useChatHistory } from '@/api/chat';
import { useChatStream } from '@/hooks/useChatStream';
import type { PdfChatPanelShellProps } from './PdfChatPanelShell';
import { useChatMessages } from './useChatMessages';
import { useChatPanelFullscreen } from './useChatPanelFullscreen';
import { useConversationManager } from './useConversationManager';

interface UsePdfChatPanelControllerOptions {
  pdfId: string;
  jumpToPage: (page: number) => void;
}

export function usePdfChatPanelController({
  pdfId,
  jumpToPage,
}: UsePdfChatPanelControllerOptions): [boolean, PdfChatPanelShellProps] {
  const {
    activeConversationId,
    isChatFullscreen,
    isChatPanelOpen,
    setActiveConversationId,
    setChatFullscreen,
    toggleChatFullscreen,
    toggleChatPanel,
  } = useChatStore();
  const { setPendingHighlight } = useChatHighlightStore();
  const userAvatarUrl = useAuthStore((state) => state.user?.avatar_url);
  const { data: history = [] } = useChatHistory(activeConversationId);
  const {
    bottomRef,
    clearStreaming,
    handleDismissFailed,
    handleKeyDown,
    handleRetry,
    handleRetryFailed,
    handleSend,
    handleStop,
    indexError,
    input,
    isSending,
    setIndexError,
    setInput,
    streamingMessage,
  } = useChatStream({
    conversationId: activeConversationId,
    invalidateQueryKeys: [
      ['chat-history', activeConversationId],
      ['chat-conversations', pdfId, undefined],
    ],
    onMessageStart: () => setIndexError(null),
    onError: (error, _isQuotaError, isIndexError) => {
      if (isIndexError) setIndexError(error);
    },
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
    pdfId,
    activeConversationId,
    setActiveConversationId,
    clearStreaming,
    autoSelectEnabled: isChatPanelOpen,
    onConversationReset: () => setIndexError(null),
  });
  const displayMessages = useChatMessages(history, streamingMessage);
  useChatPanelFullscreen(isChatPanelOpen, isChatFullscreen, setChatFullscreen);

  const closePanel = () => {
    setChatFullscreen(false);
    toggleChatPanel();
  };

  return [
    isChatPanelOpen,
    {
      activeConversationId,
      bottomRef,
      conversations,
      deletingConversation,
      displayMessages,
      emptyConversationList: !isLoadingConversations && conversations.length === 0,
      indexError,
      input,
      isCreatingConversation,
      isDeletingConversation,
      isFullscreen: isChatFullscreen,
      isSending,
      userAvatarUrl,
      onCancelDeleteConversation: cancelDeleteConversation,
      onChunkClick: (chunk) => {
        setPendingHighlight({
          pdfId,
          pageNumber: chunk.page_number,
          snippet: chunk.snippet || '',
        });
        jumpToPage(chunk.page_number);
      },
      onClose: closePanel,
      onConfirmDeleteConversation: confirmDeleteConversation,
      onDeleteConversation: requestDeleteConversation,
      onDismissFailed: handleDismissFailed,
      onInputKeyDown: handleKeyDown,
      onNewConversation: createNewConversation,
      onPageClick: jumpToPage,
      onRetry: handleRetry,
      onRetryFailed: handleRetryFailed,
      onSelectConversation: selectConversation,
      onSend: () => handleSend(),
      onSetInput: setInput,
      onStop: handleStop,
      onToggleFullscreen: toggleChatFullscreen,
    },
  ];
}
