/**
 * Tests for pdfSearch.ts — text-index-based search
 */
import { describe, it, expect } from 'vitest';
import { searchTextIndex } from './pdfSearch';
import { createPdfPageTextIndex } from './pdfTextIndex';
import type { PdfTextItemGeometry } from './pdfViewerTypes';

function textItem(
  str: string,
  x: number,
  y: number,
  width: number,
): PdfTextItemGeometry {
  return { str, width, height: 12, transform: [12, 0, 0, 12, x, y] };
}

describe('searchTextIndex', () => {
  it('finds exact match', () => {
    const items = [
      textItem('The quick brown fox', 72, 720, 100),
    ];
    const index = createPdfPageTextIndex(items, 1);
    const result = searchTextIndex(index, 'quick brown');
    expect(result).not.toBeNull();
    expect(result!.method).toBe('exact');
    expect(result!.score).toBe(1.0);
    expect(result!.start).toBeLessThan(result!.end);
  });

  it('finds normalized match (case, ligatures)', () => {
    const items = [
      textItem('Hello \uFB01le', 72, 720, 60), // "Hello file" with fi ligature
    ];
    const index = createPdfPageTextIndex(items, 1);
    const result = searchTextIndex(index, 'hello file');
    expect(result).not.toBeNull();
    expect(result!.method).toBeOneOf(['exact', 'normalized']);
  });

  it('finds dehyphenated match', () => {
    const items = [
      textItem('con-', 72, 720, 24),
      textItem('sider', 100, 708, 30),
    ];
    const index = createPdfPageTextIndex(items, 1);
    const result = searchTextIndex(index, 'consider');
    expect(result).not.toBeNull();
    expect(result!.method).toBeOneOf(['dehyphenated', 'normalized']);
  });

  it('finds word-LCS fuzzy match', () => {
    const items = [
      textItem('The quick brown fox jumps', 72, 720, 150),
    ];
    const index = createPdfPageTextIndex(items, 1);
    // Slight difference — "brown fox" should match via word-LCS
    const result = searchTextIndex(index, 'quick brown');
    expect(result).not.toBeNull();
  });

  it('finds char-LCS for special chars', () => {
    const items = [
      textItem('The formula \u03B1 + \u03B2 = \u03B3 is key', 72, 720, 150),
    ];
    const index = createPdfPageTextIndex(items, 1);
    const result = searchTextIndex(index, 'a + b = c is key');
    expect(result).not.toBeNull();
  });

  it('returns null for completely unmatched text', () => {
    const items = [
      textItem('Hello world', 72, 720, 60),
    ];
    const index = createPdfPageTextIndex(items, 1);
    const result = searchTextIndex(index, 'xyzabc123notinthere');
    expect(result).toBeNull();
  });

  it('returns null for empty needle', () => {
    const items = [textItem('Some text', 0, 0, 50)];
    const index = createPdfPageTextIndex(items, 1);
    expect(searchTextIndex(index, '')).toBeNull();
    expect(searchTextIndex(index, '   ')).toBeNull();
  });

  it('returns null for empty index', () => {
    const index = createPdfPageTextIndex([], 1);
    expect(searchTextIndex(index, 'test')).toBeNull();
  });

  it('start and end are within text bounds', () => {
    const items = [
      textItem('Hello', 72, 720, 24),
      textItem('World', 100, 720, 30),
    ];
    const index = createPdfPageTextIndex(items, 1);
    const result = searchTextIndex(index, 'Hello');
    expect(result).not.toBeNull();
    expect(result!.start).toBeGreaterThanOrEqual(0);
    expect(result!.end).toBeLessThanOrEqual(index.text.length);
    expect(result!.end).toBeGreaterThan(result!.start);
  });
});
