import { useMemo } from 'react';
import type { ChatMessage } from '@/api/chat';
import type { ChatMessageProps } from '@/components/chat/ChatMessageList';

interface StreamingMessage {
  id: string;
  role: 'assistant';
  content: string;
  context_chunks: ChatMessage['context_chunks'];
  isStreaming: boolean;
  error: string | null;
}

export function useChatMessages(
  history: ChatMessage[],
  streamingMessage: StreamingMessage | null,
): ChatMessageProps[] {
  return useMemo(
    () => [
      ...history.filter(
        (message) => !streamingMessage || message.id !== streamingMessage.id,
      ),
      ...(streamingMessage
        ? [
            {
              id: streamingMessage.id,
              role: 'assistant' as const,
              content: streamingMessage.content,
              context_chunks: streamingMessage.isStreaming
                ? null
                : streamingMessage.context_chunks,
              isStreaming: streamingMessage.isStreaming,
              error: streamingMessage.error,
            },
          ]
        : []),
    ],
    [history, streamingMessage],
  );
}
