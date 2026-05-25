import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { streamChat, type ChatMessage, type ContextChunk } from '@/api/chat'
import { useChatStore } from '@/stores/chatStore'
import { useChatStream } from './useChatStream'

vi.mock('@/api/chat', async () => {
  const actual = await vi.importActual<typeof import('@/api/chat')>('@/api/chat')
  return {
    ...actual,
    streamChat: vi.fn(),
  }
})

vi.mock('sonner', () => ({
  toast: {
    info: vi.fn(),
    error: vi.fn(),
  },
}))

const mockedStreamChat = vi.mocked(streamChat)
const mockedToast = vi.mocked(toast)

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  return { queryClient, wrapper }
}

describe('useChatStream', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useChatStore.getState().clearStreaming()
  })

  it('optimistically adds the user message and stores the streamed assistant reply', async () => {
    const { queryClient, wrapper } = createWrapper()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const chunks: ContextChunk[] = [
      {
        chunk_id: 'chunk-1',
        page_number: 4,
        snippet: 'The relevant passage.',
      },
    ]

    mockedStreamChat.mockImplementation(async (params) => {
      params.onToken('The answer ')
      params.onToken('streams.')
      params.onDone('assistant-1', chunks, true)
    })

    const { result } = renderHook(
      () => useChatStream({
        conversationId: 'conversation-1',
        invalidateQueryKeys: [['chat-history', 'conversation-1']],
      }),
      { wrapper },
    )

    await act(async () => {
      result.current.setInput(' What did the paper find? ')
    })

    await act(async () => {
      await result.current.handleSend()
    })

    expect(mockedStreamChat).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conversation-1',
      message: 'What did the paper find?',
      signal: expect.any(AbortSignal),
    }))
    expect(result.current.input).toBe('')
    expect(result.current.isSending).toBe(false)
    expect(result.current.lastMessage).toBe('What did the paper find?')
    expect(useChatStore.getState().streamingMessage).toMatchObject({
      id: 'assistant-1',
      content: 'The answer streams.',
      context_chunks: chunks,
      isStreaming: false,
    })

    const history = queryClient.getQueryData<ChatMessage[]>([
      'chat-history',
      'conversation-1',
    ])
    expect(history).toEqual([
      expect.objectContaining({
        role: 'user',
        content: 'What did the paper find?',
      }),
      expect.objectContaining({
        id: 'assistant-1',
        role: 'assistant',
        content: 'The answer streams.',
        context_chunks: chunks,
      }),
    ])
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['auto-highlight-quota'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['chat-history', 'conversation-1'] })
  })

  it('surfaces index errors without marking the stream as a generic failure', async () => {
    const { wrapper } = createWrapper()
    const onError = vi.fn()

    mockedStreamChat.mockImplementation(async (params) => {
      params.onError(new Error('Indexing is still in progress'))
    })

    const { result } = renderHook(
      () => useChatStream({ conversationId: 'conversation-1', onError }),
      { wrapper },
    )

    await act(async () => {
      await result.current.handleSend('Explain the introduction')
    })

    expect(result.current.indexError).toBe('Indexing is still in progress')
    expect(result.current.isSending).toBe(false)
    expect(onError).toHaveBeenCalledWith('Indexing is still in progress', false, true)
    expect(mockedToast.error).not.toHaveBeenCalled()
    expect(useChatStore.getState().streamingMessage?.error).toBeNull()
  })

  it('clears streaming state when an in-flight request is aborted', async () => {
    const { wrapper } = createWrapper()

    mockedStreamChat.mockImplementation(async () => {
      throw Object.assign(new Error('The operation was aborted.'), {
        name: 'AbortError',
      })
    })

    const { result } = renderHook(
      () => useChatStream({ conversationId: 'conversation-1' }),
      { wrapper },
    )

    await act(async () => {
      await result.current.handleSend('Stop this response')
    })

    expect(useChatStore.getState().streamingMessage).toBeNull()
    expect(result.current.isSending).toBe(false)
    expect(mockedToast.info).toHaveBeenCalledWith('Message generation stopped.')
  })
})
