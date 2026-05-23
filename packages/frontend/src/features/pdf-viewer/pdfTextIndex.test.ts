/**
 * Tests for pdfTextIndex.ts and pdfGeometry.ts
 */
import { describe, it, expect } from 'vitest';
import {
  buildNormMap,
  dehyphenate,
  createPdfPageTextIndex,
  normalizedRangeToOriginal,
} from './pdfTextIndex';
import { textRangeToNormalizedRects } from './pdfGeometry';
import type { PdfTextItemGeometry, PdfViewportInfo } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal mock viewport (letter page at scale=1, no rotation). */
function mockViewport(): PdfViewportInfo {
  return { width: 612, height: 792, rotation: 0, scale: 1 };
}

/** Standard horizontal text item (font size 12, positioned at x,y). */
function textItem(
  str: string,
  x: number,
  y: number,
  width: number,
): PdfTextItemGeometry {
  return {
    str,
    width,
    height: 12,
    // transform: [fontSize, 0, 0, fontSize, x, y]
    transform: [12, 0, 0, 12, x, y],
  };
}

// ---------------------------------------------------------------------------
// buildNormMap
// ---------------------------------------------------------------------------

describe('buildNormMap', () => {
  it('lowercases and collapses whitespace', () => {
    const { norm, toOrig } = buildNormMap('Hello  World');
    expect(norm).toBe('hello world');
    // 'H'(0) -> 'h', 'e'(1), 'l'(2), 'l'(3), 'o'(4), ' '(5) (first space), ' '(6) (collapsed), 'W'(7), 'o'(8), 'r'(9), 'l'(10), 'd'(11)
    expect(toOrig.length).toBe(11);
    expect(toOrig[0]).toBe(0); // h -> H
    expect(toOrig[5]).toBe(5); // first space
    expect(toOrig[6]).toBe(7); // w -> W
  });

  it('expands fi ligature', () => {
    const { norm } = buildNormMap('\uFB01le'); // fi ligature + 'le'
    expect(norm).toBe('file');
  });

  it('expands fl ligature', () => {
    const { norm } = buildNormMap('\uFB02at'); // fl ligature + 'at'
    expect(norm).toBe('flat');
  });

  it('expands ff ligature', () => {
    const { norm } = buildNormMap('\uFB00icient'); // ff ligature → 'ff' + 'icient'
    expect(norm).toBe('fficient');
  });

  it('normalizes curly quotes', () => {
    const { norm } = buildNormMap('\u201CHello\u201D');
    expect(norm).toBe('"hello"');
  });

  it('normalizes em and en dashes', () => {
    const { norm } = buildNormMap('A\u2013B\u2014C');
    expect(norm).toBe('a-b-c');
  });

  it('strips zero-width chars', () => {
    const { norm } = buildNormMap('hel\u200Blo');
    expect(norm).toBe('hello');
  });

  it('builds correct toOrig mapping', () => {
    const original = 'Test Case';
    const { norm, toOrig } = buildNormMap(original);
    expect(norm).toBe('test case');
    // Every output char must map back to a valid original index
    for (let i = 0; i < toOrig.length; i++) {
      expect(toOrig[i]).toBeGreaterThanOrEqual(0);
      expect(toOrig[i]).toBeLessThan(original.length);
    }
  });

  it('preserves order in toOrig', () => {
    const { toOrig } = buildNormMap('abc def');
    for (let i = 1; i < toOrig.length; i++) {
      expect(toOrig[i]).toBeGreaterThanOrEqual(toOrig[i - 1]);
    }
  });
});

// ---------------------------------------------------------------------------
// dehyphenate
// ---------------------------------------------------------------------------

describe('dehyphenate', () => {
  it('strips line-break hyphens', () => {
    const { text } = dehyphenate('con- sider');
    expect(text).toBe('consider');
  });

  it('keeps normal hyphens', () => {
    const { text } = dehyphenate('state-of-the-art');
    expect(text).toBe('state-of-the-art');
  });

  it('keeps hyphen at start of text', () => {
    const { text } = dehyphenate('-foo bar');
    expect(text).toBe('-foo bar');
  });

  it('strips hyphen with numeric continuation (word break)', () => {
    // \w matches digits too, so "sec- 3.2" is treated as a hyphenated break
    const { text } = dehyphenate('sec- 3.2 results');
    expect(text).toBe('sec3.2 results');
  });

  it('builds correct toNormal mapping', () => {
    const input = 'con- sider later';
    const { text, toNormal } = dehyphenate(input);
    expect(text).toBe('consider later');
    expect(toNormal[0]).toBe(0); // 'c' maps to input[0]
    // The loop skips '- ' at indices 3-5, so 's' at output[3] maps to input[5]
    expect(toNormal[3]).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// createPdfPageTextIndex
// ---------------------------------------------------------------------------

describe('createPdfPageTextIndex', () => {
  it('concatenates items into stable page text', () => {
    const items = [
      textItem('Hello', 72, 720, 30),
      textItem('World', 108, 720, 35),
    ];
    const index = createPdfPageTextIndex(items, 1);
    expect(index.text).toBe('Hello World');
  });

  it('preserves items array', () => {
    const items = [textItem('ab', 0, 0, 10), textItem('cd', 20, 0, 10)];
    const index = createPdfPageTextIndex(items, 1);
    expect(index.items).toHaveLength(2);
    expect(index.items[0].str).toBe('ab');
  });

  it('builds correct itemCharRanges', () => {
    const items = [
      textItem('ab', 0, 0, 10),
      textItem('cd', 30, 0, 10),
    ];
    const index = createPdfPageTextIndex(items, 1);
    // "ab cd" -> ab(0,2) space(2,3) cd(3,5)
    expect(index.itemCharRanges[0]).toEqual({ start: 0, end: 2 });
    expect(index.itemCharRanges[1]).toEqual({ start: 3, end: 5 });
  });

  it('builds normalizedText', () => {
    const items = [textItem('Hello', 72, 720, 30)];
    const index = createPdfPageTextIndex(items, 1);
    expect(index.normalizedText).toBe('hello');
  });

  it('builds normalizedToOriginal mapping', () => {
    const items = [textItem('Hi', 72, 720, 10)];
    const index = createPdfPageTextIndex(items, 1);
    expect(index.normalizedToOriginal.length).toBe(index.normalizedText.length);
    expect(index.normalizedToOriginal[0]).toBe(0); // 'h' -> 'H' at 0
  });

  it('builds originalToItem for every character', () => {
    const items = [
      textItem('ab', 0, 0, 10),
      textItem('cd', 30, 0, 10),
    ];
    const index = createPdfPageTextIndex(items, 1);
    // text = "ab cd" (5 chars)
    for (let i = 0; i < index.text.length; i++) {
      expect(index.originalToItem[i]).toBeDefined();
      expect(typeof index.originalToItem[i].itemIndex).toBe('number');
      expect(typeof index.originalToItem[i].offset).toBe('number');
    }
  });

  it('maps first item chars to item 0', () => {
    const items = [
      textItem('first', 0, 0, 30),
      textItem('second', 50, 0, 40),
    ];
    const index = createPdfPageTextIndex(items, 1);
    // "first second" — first 5 chars should be item 0
    for (let i = 0; i < 5; i++) {
      expect(index.originalToItem[i].itemIndex).toBe(0);
    }
  });

  it('sets pageNumber', () => {
    const index = createPdfPageTextIndex([textItem('a', 0, 0, 5)], 42);
    expect(index.pageNumber).toBe(42);
  });

  it('text length equals sum of item strings plus inter-item spaces', () => {
    const items = [
      textItem('a', 0, 0, 5),
      textItem('b', 10, 0, 5),
      textItem('c', 20, 0, 5),
    ];
    const index = createPdfPageTextIndex(items, 1);
    expect(index.text).toBe('a b c');
    expect(index.text.length).toBe(5); // 'a' + ' ' + 'b' + ' ' + 'c'
  });

  it('does not add space when border already has whitespace', () => {
    const items = [
      textItem('a ', 0, 0, 10),
      textItem('b', 20, 0, 5),
    ];
    const index = createPdfPageTextIndex(items, 1);
    expect(index.text).toBe('a b');
  });
});

// ---------------------------------------------------------------------------
// normalizedRangeToOriginal
// ---------------------------------------------------------------------------

describe('normalizedRangeToOriginal', () => {
  it('maps normalized range to original range', () => {
    const items = [textItem('Hello World', 72, 720, 80)];
    const index = createPdfPageTextIndex(items, 1);
    // "Hello World" normalized -> "hello world"
    // Find "world" in normalized (indices 6-11)
    const result = normalizedRangeToOriginal(index, 6, 11);
    expect(result).not.toBeNull();
    expect(result!.start).toBe(6); // 'W' in original
    expect(result!.end).toBe(11);
  });

  it('returns null for out-of-bounds range', () => {
    const items = [textItem('abc', 0, 0, 20)];
    const index = createPdfPageTextIndex(items, 1);
    const result = normalizedRangeToOriginal(index, 100, 105);
    expect(result).toBeNull();
  });

  it('returns null for empty range', () => {
    const items = [textItem('abc', 0, 0, 20)];
    const index = createPdfPageTextIndex(items, 1);
    const result = normalizedRangeToOriginal(index, 0, 0);
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// textRangeToNormalizedRects
// ---------------------------------------------------------------------------

describe('textRangeToNormalizedRects', () => {
  describe('basic rect computation', () => {
    it('returns a rect for a full item range', () => {
      const items = [textItem('Hello', 72, 720, 30)];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 0, 5, mockViewport());
      expect(rects.length).toBe(1);
      expect(rects[0].x).toBeCloseTo(72 / 612);
      expect(rects[0].y).toBeCloseTo((792 - 720 - 12) / 792);
      expect(rects[0].w).toBeCloseTo(30 / 612);
    });

    it('returns a narrower rect for a partial item range', () => {
      const items = [textItem('HelloWorld', 100, 700, 60)];
      const index = createPdfPageTextIndex(items, 1);
      // Only select "Hello" (first 5 chars)
      const fullRect = textRangeToNormalizedRects(index, 0, 10, mockViewport());
      const partialRect = textRangeToNormalizedRects(
        index,
        0,
        5,
        mockViewport(),
      );
      expect(partialRect.length).toBe(1);
      // Partial width should be ~half of full width
      expect(partialRect[0].w).toBeLessThan(fullRect[0].w);
      // Partial x should be same as full x (both start at 0)
      expect(partialRect[0].x).toBeCloseTo(fullRect[0].x);
    });

    it('returns multiple rects for multi-item ranges', () => {
      const items = [
        textItem('first', 72, 700, 30),
        textItem('second', 130, 700, 40),
      ];
      const index = createPdfPageTextIndex(items, 1);
      // Select "first second" = full text
      const rects = textRangeToNormalizedRects(
        index,
        0,
        index.text.length,
        mockViewport(),
      );
      // Should be 1 rect after merging (since they're on same line)
      expect(rects.length).toBe(1);
    });

    it('returns empty array for empty range', () => {
      const items = [textItem('test', 0, 0, 20)];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 0, 0, mockViewport());
      expect(rects).toHaveLength(0);
    });

    it('returns empty array for reversed range', () => {
      const items = [textItem('test', 0, 0, 20)];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 5, 0, mockViewport());
      expect(rects).toHaveLength(0);
    });

    it('returns empty array for invalid viewport', () => {
      const items = [textItem('test', 0, 0, 20)];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 0, 4, {
        ...mockViewport(),
        width: 0,
      });
      expect(rects).toHaveLength(0);
    });
  });

  describe('rect normalization', () => {
    it('normalizes x and w by page width', () => {
      const items = [textItem('ab', 306, 700, 24)]; // 306 = half of 612
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 0, 2, mockViewport());
      expect(rects[0].x).toBeCloseTo(0.5, 2);
    });

    it('normalizes y and h by page height', () => {
      const items = [textItem('ab', 72, 396, 12)]; // 396 = half of 792
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 0, 2, mockViewport());
      expect(rects[0].y).toBeCloseTo((792 - 396 - 12) / 792);
      expect(rects[0].h).toBeCloseTo(12 / 792);
    });

    it('rects are within 0..1 range', () => {
      const items = [textItem('test text here', 50, 50, 80)];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(index, 0, index.text.length, mockViewport());
      for (const r of rects) {
        expect(r.x).toBeGreaterThanOrEqual(0);
        expect(r.x).toBeLessThanOrEqual(1);
        expect(r.y).toBeGreaterThanOrEqual(0);
        expect(r.y).toBeLessThanOrEqual(1);
        expect(r.w).toBeGreaterThan(0);
        expect(r.h).toBeGreaterThan(0);
      }
    });
  });

  describe('rect merging', () => {
    it('merges adjacent rects on the same line', () => {
      // Two items next to each other horizontally, same y
      const items = [
        textItem('left', 50, 700, 25),
        textItem('right', 80, 700, 30),
      ];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(
        index,
        0,
        index.text.length,
        mockViewport(),
      );
      expect(rects.length).toBe(1);
    });

    it('does not merge rects on different lines', () => {
      const items = [
        textItem('line1', 50, 700, 25),
        textItem('line2', 50, 680, 25),
      ];
      const index = createPdfPageTextIndex(items, 1);
      const rects = textRangeToNormalizedRects(
        index,
        0,
        index.text.length,
        mockViewport(),
      );
      expect(rects.length).toBe(2);
    });
  });

  describe('whitespace trimming', () => {
    it('trims leading whitespace from selected items', () => {
      const items = [textItem('  hello  ', 72, 720, 50)];
      const index = createPdfPageTextIndex(items, 1);
      // Select from char 2 to char 7 ("hello")
      const rects = textRangeToNormalizedRects(index, 2, 7, mockViewport());
      expect(rects.length).toBe(1);
    });
  });

  describe('multi-item partial selection', () => {
    it('returns rects for select text spanning multiple items', () => {
      const items = [
        textItem('abc', 72, 700, 18),
        textItem('def', 95, 700, 18),
        textItem('ghi', 118, 700, 18),
      ];
      const index = createPdfPageTextIndex(items, 1);
      // Select 'b' through 'f' (char 1 to char 7 in "abc def ghi")
      const rects = textRangeToNormalizedRects(index, 1, 7, mockViewport());
      expect(rects.length).toBeGreaterThan(0);
    });
  });
});

// ---------------------------------------------------------------------------
// Integration: index → geometry round‑trip
// ---------------------------------------------------------------------------

describe('index to geometry round-trip', () => {
  it('creates valid normalized rects from realistic text items', () => {
    const items: PdfTextItemGeometry[] = [
      {
        str: 'The',
        width: 18.2,
        height: 9.9,
        transform: [10, 0, 0, 10, 72, 708],
      },
      {
        str: 'quick',
        width: 25.3,
        height: 9.9,
        transform: [10, 0, 0, 10, 95, 708],
      },
      {
        str: 'brown',
        width: 27.8,
        height: 9.9,
        transform: [10, 0, 0, 10, 125, 708],
      },
      {
        str: 'fox',
        width: 15.6,
        height: 9.9,
        transform: [10, 0, 0, 10, 157, 708],
      },
    ];

    const index = createPdfPageTextIndex(items, 1);
    expect(index.text).toBe('The quick brown fox');

    // Full range
    const fullRects = textRangeToNormalizedRects(
      index,
      0,
      index.text.length,
      mockViewport(),
    );
    // All on same line → one merged rect
    expect(fullRects.length).toBe(1);

    // Select "quick brown" only (chars 4..16)
    const partialRects = textRangeToNormalizedRects(
      index,
      4,
      16,
      mockViewport(),
    );
    expect(partialRects.length).toBe(1);
    expect(partialRects[0].x).toBeGreaterThan(0);
    expect(partialRects[0].w).toBeLessThan(fullRects[0].w);
  });

  it('handles dehyphenated search resolution', () => {
    // Simulate items from a PDF with a line-break hyphen
    const items: PdfTextItemGeometry[] = [
      textItem('con-', 72, 708, 24),
      textItem('sider', 100, 690, 30),
    ];
    const index = createPdfPageTextIndex(items, 1);
    // "con- sider" is the raw text
    expect(index.text).toBe('con- sider');
    // Normalized text should be "con- sider"
    // Dehyphenated should be "consider"

    const { text: dehyphed } = dehyphenate(index.normalizedText);
    expect(dehyphed).toBe('consider');
  });
});
