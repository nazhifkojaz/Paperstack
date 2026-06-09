import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@/test/test-utils';
import { createMockAnnotation } from '@/test/test-utils';
import { AnnotationDetailDrawer } from './AnnotationDetailDrawer';

const mocks = vi.hoisted(() => ({
  updateMutate: vi.fn(),
  explain: vi.fn(),
  paraphrase: vi.fn(),
}));

vi.mock('@/api/annotations', () => ({
  useUpdateAnnotation: vi.fn(() => ({
    mutate: mocks.updateMutate,
    isPending: false,
  })),
}));

vi.mock('./useAnnotationExplain', () => ({
  useAnnotationExplain: vi.fn(() => ({
    isExplaining: false,
    explainingId: null,
    statusMessage: '',
    explain: mocks.explain,
    clearExplain: vi.fn(),
    explainUsesRemaining: null,
  })),
}));

vi.mock('./useAnnotationParaphrase', () => ({
  useAnnotationParaphrase: vi.fn(() => ({
    isParaphrasing: false,
    paraphrasingId: null,
    statusMessage: '',
    paraphrase: mocks.paraphrase,
    clearParaphrase: vi.fn(),
    explainUsesRemaining: null,
  })),
}));

function renderDrawer(annotation: ReturnType<typeof createMockAnnotation>) {
  return render(
    <AnnotationDetailDrawer
      annotation={annotation}
      pdfId="pdf-1"
      open
      onOpenChange={vi.fn()}
    />,
  );
}

function selectTab(name: RegExp) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.pointerDown(tab, { button: 0, ctrlKey: false, pointerType: 'mouse' });
  fireEvent.mouseDown(tab, { button: 0, ctrlKey: false });
  fireEvent.mouseUp(tab);
  fireEvent.click(tab);
}

describe('AnnotationDetailDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows only the AI action controls for the selected tab', () => {
    const annotation = createMockAnnotation({
      selected_text: 'selected text',
      note_content: 'user note',
      metadata: {
        ai_explanation: { content: 'Generated explanation.' },
        ai_paraphrase: { content: 'Generated paraphrase.', level: 'same' },
      },
    });

    renderDrawer(annotation);

    expect(screen.queryByRole('button', { name: /re-explain/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /rephrase/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Same level')).not.toBeInTheDocument();

    selectTab(/explanation/i);

    expect(screen.getByRole('button', { name: /re-explain/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /rephrase/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Same level')).not.toBeInTheDocument();

    selectTab(/paraphrase/i);

    expect(screen.queryByRole('button', { name: /re-explain/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /rephrase/i })).toBeInTheDocument();
    expect(screen.getAllByText('Same level').length).toBeGreaterThan(0);
  });

  it('keeps the explanation tab selected when the explanation result arrives', async () => {
    const annotation = createMockAnnotation({
      selected_text: 'selected text',
      note_content: 'user note',
    });
    const { rerender } = renderDrawer(annotation);

    selectTab(/explanation/i);
    expect(screen.getByRole('tab', { name: /explanation/i })).toHaveAttribute('data-state', 'active');

    rerender(
      <AnnotationDetailDrawer
        annotation={{
          ...annotation,
          metadata: {
            ai_explanation: { content: 'Generated explanation.' },
          },
        }}
        pdfId="pdf-1"
        open
        onOpenChange={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /explanation/i })).toHaveAttribute('data-state', 'active');
    });
  });

  it('keeps the paraphrase tab selected when the paraphrase result arrives', async () => {
    const annotation = createMockAnnotation({
      selected_text: 'selected text',
      note_content: 'user note',
    });
    const { rerender } = renderDrawer(annotation);

    selectTab(/paraphrase/i);
    expect(screen.getByRole('tab', { name: /paraphrase/i })).toHaveAttribute('data-state', 'active');

    rerender(
      <AnnotationDetailDrawer
        annotation={{
          ...annotation,
          metadata: {
            ai_paraphrase: { content: 'Generated paraphrase.', level: 'same' },
          },
        }}
        pdfId="pdf-1"
        open
        onOpenChange={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /paraphrase/i })).toHaveAttribute('data-state', 'active');
    });
  });
});
