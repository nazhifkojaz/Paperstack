import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createMockAnnotation } from '@/test/test-utils';
import { useAnnotationParaphrase } from './useAnnotationParaphrase';

const mocks = vi.hoisted(() => ({
  paraphraseMutate: vi.fn(),
}));

vi.mock('@/api/chat', () => ({
  useParaphraseAnnotation: () => ({
    mutate: mocks.paraphraseMutate,
  }),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return { queryClient, wrapper };
}

describe('useAnnotationParaphrase', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('updates every cached annotations query containing the paraphrased annotation', () => {
    const { queryClient, wrapper } = createWrapper();
    const annotation = createMockAnnotation({
      id: 'ann-1',
      set_id: 'set-1',
      selected_text: 'passage to paraphrase',
      note_content: null,
      metadata: null,
    });

    queryClient.setQueryData(['annotations', 'set-1'], [annotation]);
    queryClient.setQueryData(['annotations', 'paper-layer-cache'], [annotation]);
    const unrelatedAnnotations = [
      createMockAnnotation({
        id: 'ann-2',
        set_id: 'set-2',
        selected_text: 'other passage',
      }),
    ];
    queryClient.setQueryData(['annotations', 'set-2'], unrelatedAnnotations);

    const { result } = renderHook(() => useAnnotationParaphrase(), { wrapper });

    act(() => {
      result.current.paraphrase(annotation, 'pdf-1', 'plain');
    });

    expect(mocks.paraphraseMutate.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        annotation_id: 'ann-1',
        level: 'plain',
      }),
    );

    const onSuccess = mocks.paraphraseMutate.mock.calls[0][1].onSuccess;
    act(() => {
      onSuccess({
        paraphrase: 'Generated paraphrase.',
        note_content: null,
        metadata: {
          ai_paraphrase: {
            content: 'Generated paraphrase.',
            generated_at: '2026-06-08 14:00 UTC',
            level: 'plain',
          },
        },
        explain_uses_remaining: -1,
      });
    });

    expect(queryClient.getQueryData(['annotations', 'set-1'])).toEqual([
      expect.objectContaining({
        id: 'ann-1',
        metadata: expect.objectContaining({
          ai_paraphrase: expect.objectContaining({
            content: 'Generated paraphrase.',
            level: 'plain',
          }),
        }),
      }),
    ]);
    expect(queryClient.getQueryData(['annotations', 'paper-layer-cache'])).toEqual([
      expect.objectContaining({
        id: 'ann-1',
        metadata: expect.objectContaining({
          ai_paraphrase: expect.objectContaining({
            content: 'Generated paraphrase.',
            level: 'plain',
          }),
        }),
      }),
    ]);
    expect(queryClient.getQueryData(['annotations', 'set-2'])).toBe(unrelatedAnnotations);
  });
});
