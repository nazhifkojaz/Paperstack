import type { Annotation } from '@/api/annotations';

export function applyAiResultToAnnotation(
  annotationId: string,
  noteContent: string | null,
  metadata: Record<string, unknown> | null | undefined,
) {
  return (old: Annotation[] | undefined): Annotation[] | undefined => {
    if (!old) return old;
    let changed = false;
    const next = old.map((annotation) => {
      if (annotation.id !== annotationId) return annotation;
      changed = true;
      return {
        ...annotation,
        note_content: noteContent,
        metadata: metadata ?? annotation.metadata,
      };
    });
    return changed ? next : old;
  };
}
