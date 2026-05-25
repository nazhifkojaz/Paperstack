import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  type Conversation,
} from '@/api/chat';

interface DeletingConversation {
  id: string;
  title: string;
}

interface UseConversationManagerOptions {
  pdfId?: string;
  collectionId?: string;
  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;
  clearStreaming: () => void;
  autoSelectEnabled?: boolean;
  onConversationReset?: () => void;
}

export function useConversationManager({
  pdfId,
  collectionId,
  activeConversationId,
  setActiveConversationId,
  clearStreaming,
  autoSelectEnabled = true,
  onConversationReset,
}: UseConversationManagerOptions) {
  const queryClient = useQueryClient();
  const [deletingConversation, setDeletingConversation] =
    useState<DeletingConversation | null>(null);
  const { data: conversations = [], isLoading } = useConversations(
    pdfId,
    collectionId,
  );
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const conversationQueryKey = ['chat-conversations', pdfId, collectionId] as const;

  useEffect(() => {
    if (!autoSelectEnabled || isLoading || activeConversationId) return;
    if (conversations.length > 0) {
      setActiveConversationId(conversations[0].id);
    }
  }, [
    activeConversationId,
    autoSelectEnabled,
    conversations,
    isLoading,
    setActiveConversationId,
  ]);

  const resetStreaming = () => {
    clearStreaming();
    onConversationReset?.();
  };

  const selectConversation = (conversationId: string) => {
    setActiveConversationId(conversationId);
    clearStreaming();
  };

  const createNewConversation = async () => {
    if (!pdfId && !collectionId) return;

    try {
      const conversation = await createConversation.mutateAsync({
        ...(pdfId ? { pdf_id: pdfId } : {}),
        ...(collectionId ? { collection_id: collectionId } : {}),
      });
      queryClient.setQueryData<Conversation[]>(
        conversationQueryKey,
        (old = []) => [
          conversation,
          ...old.filter((item) => item.id !== conversation.id),
        ],
      );
      setActiveConversationId(conversation.id);
      resetStreaming();
    } catch {
      toast.error('Failed to create conversation');
    }
  };

  const requestDeleteConversation = (conversationId: string, title: string) => {
    setDeletingConversation({ id: conversationId, title });
  };

  const confirmDeleteConversation = async () => {
    if (!deletingConversation) return;

    const { id } = deletingConversation;
    try {
      await deleteConversation.mutateAsync(id);
      queryClient.setQueryData<Conversation[]>(conversationQueryKey, (old = []) =>
        old.filter((conversation) => conversation.id !== id),
      );
      if (activeConversationId === id) {
        setActiveConversationId(null);
        resetStreaming();
      }
    } catch {
      toast.error('Failed to delete conversation');
    } finally {
      setDeletingConversation(null);
    }
  };

  return {
    cancelDeleteConversation: () => setDeletingConversation(null),
    confirmDeleteConversation,
    conversations,
    createNewConversation,
    deletingConversation,
    isCreatingConversation: createConversation.isPending,
    isDeletingConversation: deleteConversation.isPending,
    isLoadingConversations: isLoading,
    requestDeleteConversation,
    selectConversation,
  };
}
