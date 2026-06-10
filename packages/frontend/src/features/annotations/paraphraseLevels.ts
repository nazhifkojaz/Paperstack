import type { ParaphraseLevel } from '@/api/chat';

export const PARAPHRASE_LEVELS: Array<{
  value: ParaphraseLevel;
  label: string;
}> = [
  { value: 'same', label: 'Same level' },
  { value: 'simpler', label: 'Simpler' },
  { value: 'plain', label: 'Plain language' },
];

export function getParaphraseLevelLabel(level?: string | null): string | null {
  if (!level) return null;
  return PARAPHRASE_LEVELS.find((item) => item.value === level)?.label ?? null;
}
