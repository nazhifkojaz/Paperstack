interface AnnotationColor {
  color: string;
  label: string;
}

export const ANNOTATION_COLORS: readonly AnnotationColor[] = [
  { color: '#EF4444', label: 'Red' },
  { color: '#3B82F6', label: 'Blue' },
  { color: '#22C55E', label: 'Green' },
  { color: '#FFFF00', label: 'Yellow' },
  { color: '#F97316', label: 'Orange' },
  { color: '#A855F7', label: 'Purple' },
  { color: '#FF00FF', label: 'Magenta' },
  { color: '#00FFFF', label: 'Cyan' },
] as const;
