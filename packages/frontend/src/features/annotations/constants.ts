interface AnnotationColor {
  color: string;
  label: string;
}

export const DEFAULT_HIGHLIGHT_COLOR = '#FFFF00' as const;

export const ANNOTATION_COLORS: readonly AnnotationColor[] = [
  { color: '#22c55e', label: 'Findings' },
  { color: '#3b82f6', label: 'Methods' },
  { color: '#a855f7', label: 'Definitions' },
  { color: '#f97316', label: 'Limitations' },
  { color: '#6b7280', label: 'Background' },
  { color: '#FFFF00', label: 'Highlights' },
  { color: '#EF4444', label: 'Important' },
  { color: '#00FFFF', label: 'Follow-up' },
] as const;

export const DEFAULT_COLOR_LABELS: Readonly<Record<string, string>> = Object.fromEntries(
  ANNOTATION_COLORS.map(({ color, label }) => [color, label]),
);
