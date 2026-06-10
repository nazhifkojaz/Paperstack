import type { Annotation } from '@/api/annotations';

export interface AnnotationAiExplanation {
  content: string;
  generated_at?: string;
  context_chunks?: Array<{
    chunk_id: string;
    page_number: number;
    snippet: string;
  }>;
}

export interface AnnotationAiParaphrase {
  content: string;
  generated_at?: string;
  level?: string;
}

const LEGACY_AI_BLOCK_PATTERN =
  '(?:^|\\n{2,})\\[AI Explanation\\s*[—-]\\s*([^\\]]+)\\]\\s*([\\s\\S]*?)(?=\\n{2,}\\[AI Explanation\\s*[—-]|\\s*$)';

function legacyAiBlockRegex() {
  return new RegExp(LEGACY_AI_BLOCK_PATTERN, 'g');
}

function getMetadata(annotation: Annotation): Record<string, unknown> {
  return annotation.metadata && typeof annotation.metadata === 'object'
    ? { ...annotation.metadata }
    : {};
}

function isAiGeneratedContent(value: unknown): value is { content: string } {
  return (
    !!value &&
    typeof value === 'object' &&
    'content' in value &&
    typeof (value as { content?: unknown }).content === 'string'
  );
}

export function getAnnotationAiExplanation(
  annotation: Annotation,
): AnnotationAiExplanation | null {
  const metadataAi = getMetadata(annotation).ai_explanation;
  if (isAiGeneratedContent(metadataAi)) return metadataAi as AnnotationAiExplanation;

  const legacyBlocks = parseLegacyAiExplanations(annotation.note_content ?? '');
  return legacyBlocks.length > 0 ? legacyBlocks[legacyBlocks.length - 1] : null;
}

export function getAnnotationAiParaphrase(
  annotation: Annotation,
): AnnotationAiParaphrase | null {
  const metadataAi = getMetadata(annotation).ai_paraphrase;
  return isAiGeneratedContent(metadataAi) ? metadataAi as AnnotationAiParaphrase : null;
}

export function getAnnotationUserNote(annotation: Annotation): string {
  return stripLegacyAiExplanations(annotation.note_content ?? '');
}

export function hasAnnotationSupplementalContent(annotation: Annotation): boolean {
  return (
    !!getAnnotationUserNote(annotation) ||
    !!getAnnotationAiExplanation(annotation) ||
    !!getAnnotationAiParaphrase(annotation)
  );
}

export function getAnnotationSupplementalTitle(annotation: Annotation): string {
  return (
    getAnnotationUserNote(annotation) ||
    getAnnotationAiExplanation(annotation)?.content ||
    getAnnotationAiParaphrase(annotation)?.content ||
    ''
  );
}

export function buildNoteUpdateData(
  annotation: Annotation,
  noteContent: string,
): Partial<Annotation> {
  const metadata = getMetadata(annotation);
  const legacyAi = getAnnotationAiExplanation(annotation);

  if (!metadata.ai_explanation && legacyAi) {
    metadata.ai_explanation = legacyAi;
  }

  return {
    note_content: noteContent.trim() ? noteContent : null,
    ...(Object.keys(metadata).length > 0 ? { metadata } : {}),
  };
}

export function parseLegacyAiExplanations(
  noteContent: string,
): AnnotationAiExplanation[] {
  const matches: AnnotationAiExplanation[] = [];
  const regex = legacyAiBlockRegex();
  let match: RegExpExecArray | null;

  while ((match = regex.exec(noteContent)) !== null) {
    const content = match[2]?.trim();
    if (!content) continue;
    matches.push({
      generated_at: match[1]?.trim(),
      content,
    });
  }

  return matches;
}

export function stripLegacyAiExplanations(noteContent: string): string {
  return noteContent.replace(legacyAiBlockRegex(), '').trim();
}
