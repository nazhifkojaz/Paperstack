import { describe, expect, it } from 'vitest';
import { createMockAnnotation } from '@/test/test-utils';
import {
  buildNoteUpdateData,
  getAnnotationAiExplanation,
  getAnnotationUserNote,
  hasAnnotationSupplementalContent,
} from './annotationContent';

describe('annotationContent', () => {
  it('splits legacy AI explanation blocks from user notes', () => {
    const annotation = createMockAnnotation({
      note_content:
        'my note\n\n[AI Explanation - 2026-04-25 13:20 UTC]\nGenerated explanation.',
    });

    expect(getAnnotationUserNote(annotation)).toBe('my note');
    expect(getAnnotationAiExplanation(annotation)).toEqual({
      generated_at: '2026-04-25 13:20 UTC',
      content: 'Generated explanation.',
    });
  });

  it('prefers metadata-backed AI explanations', () => {
    const annotation = createMockAnnotation({
      note_content:
        '[AI Explanation - 2026-04-25 13:20 UTC]\nLegacy explanation.',
      metadata: {
        ai_explanation: {
          generated_at: '2026-05-01 10:00 UTC',
          content: 'Metadata explanation.',
        },
      },
    });

    expect(getAnnotationAiExplanation(annotation)?.content).toBe('Metadata explanation.');
  });

  it('preserves legacy AI explanation metadata when saving user notes', () => {
    const annotation = createMockAnnotation({
      note_content:
        'old note\n\n[AI Explanation - 2026-04-25 13:20 UTC]\nGenerated explanation.',
    });

    expect(buildNoteUpdateData(annotation, 'new note')).toEqual({
      note_content: 'new note',
      metadata: {
        ai_explanation: {
          generated_at: '2026-04-25 13:20 UTC',
          content: 'Generated explanation.',
        },
      },
    });
  });

  it('detects either user notes or AI explanations as supplemental content', () => {
    expect(hasAnnotationSupplementalContent(createMockAnnotation())).toBe(false);
    expect(hasAnnotationSupplementalContent(createMockAnnotation({ note_content: 'note' }))).toBe(true);
    expect(hasAnnotationSupplementalContent(createMockAnnotation({
      metadata: { ai_explanation: { content: 'AI' } },
    }))).toBe(true);
  });
});
