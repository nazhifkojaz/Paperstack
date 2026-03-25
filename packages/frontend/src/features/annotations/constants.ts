/**
 * Shared constants for annotation features.
 * Centralizes color palettes, display options, and annotation-specific values.
 */

/**
 * A preset color for annotation highlighting.
 * Each color has a hex value and a human-readable label.
 */
export interface AnnotationColor {
  /** Hex color code (e.g., "#EF4444") */
  color: string;
  /** Human-readable label for accessibility and tooltips */
  label: string;
}

/**
 * Standard annotation color palette.
 * Used across all annotation UI components for consistency.
 *
 * Order matters: these appear in toolbars and context menus in this sequence.
 * Merged from the two previously separate palettes (Toolbar had 6, ContextMenu had 8).
 * This unified palette includes all colors from both sources.
 */
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

/**
 * Type guard to check if a string is a valid annotation color.
 *
 * @param color - The color string to validate
 * @returns true if the color is in the ANNOTATION_COLORS palette
 *
 * @example
 * if (isValidAnnotationColor(userColor)) {
 *   updateAnnotation({ color: userColor });
 * }
 */
export function isValidAnnotationColor(color: string): color is AnnotationColor['color'] {
  return ANNOTATION_COLORS.some(c => c.color === color);
}

/**
 * Gets the label for a given color hex value.
 * Returns undefined if the color is not in the palette.
 *
 * @param color - The color hex to look up
 * @returns The label for the color, or undefined if not found
 *
 * @example
 * const label = getColorLabel('#EF4444'); // 'Red'
 */
export function getColorLabel(color: string): string | undefined {
  return ANNOTATION_COLORS.find(c => c.color === color)?.label;
}
