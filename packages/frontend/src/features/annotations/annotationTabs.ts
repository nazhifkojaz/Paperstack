export type AnnotationContentTab = 'note' | 'explanation' | 'paraphrase';

export function getDefaultAnnotationContentTab(
  userNote: string,
  hasAiExplanation: boolean,
  hasAiParaphrase: boolean,
): AnnotationContentTab {
  if (!userNote && hasAiExplanation) return 'explanation';
  if (!userNote && hasAiParaphrase) return 'paraphrase';
  return 'note';
}
