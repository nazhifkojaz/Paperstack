import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createMockAnnotation } from '@/test/test-utils';
import { useAnnotationExplain } from './useAnnotationExplain';

const mocks = vi.hoisted(() => ({
  explainMutate: vi.fn(),
}));

vi.mock('@/api/chat', () => ({
  useExplainAnnotation: () => ({
    mutate: mocks.explainMutate,
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

describe('useAnnotationExplain', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('updates every cached annotations query containing the explained annotation', () => {
    const { queryClient, wrapper } = createWrapper();
    const annotation = createMockAnnotation({
      id: 'ann-1',
      set_id: 'set-1',
      selected_text: 'passage to explain',
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

    const { result } = renderHook(() => useAnnotationExplain(), { wrapper });

    act(() => {
      result.current.explain(annotation, 'pdf-1');
    });

    const onSuccess = mocks.explainMutate.mock.calls[0][1].onSuccess;
    act(() => {
      onSuccess({
        explanation: 'Generated explanation.',
        note_content: null,
        metadata: {
          ai_explanation: {
            content: 'Generated explanation.',
            generated_at: '2026-06-08 14:00 UTC',
          },
        },
        explain_uses_remaining: -1,
      });
    });

    expect(queryClient.getQueryData(['annotations', 'set-1'])).toEqual([
      expect.objectContaining({
        id: 'ann-1',
        metadata: expect.objectContaining({
          ai_explanation: expect.objectContaining({
            content: 'Generated explanation.',
          }),
        }),
      }),
    ]);
    expect(queryClient.getQueryData(['annotations', 'paper-layer-cache'])).toEqual([
      expect.objectContaining({
        id: 'ann-1',
        metadata: expect.objectContaining({
          ai_explanation: expect.objectContaining({
            content: 'Generated explanation.',
          }),
        }),
      }),
    ]);
    expect(queryClient.getQueryData(['annotations', 'set-2'])).toBe(unrelatedAnnotations);
  });
});
