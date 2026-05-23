// ---------------------------------------------------------------------------
// pdfGeometry.ts — Text-range → normalized rect projection
// ---------------------------------------------------------------------------
// Pure utility.  Uses PDF text-item transforms and viewport dimensions.
// No DOM, no React, no Range.getClientRects().
// ---------------------------------------------------------------------------

import type { NormalizedRect, PdfPageTextIndex, PdfViewportInfo } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Text range → normalized rects
// ---------------------------------------------------------------------------

/**
 * Convert a character range [start, end) in the **raw page text** to an
 * array of page‑normalized rects (0..1).
 *
 * For each text item that intersects the range the function computes a
 * rect from the item's pdf.js transform.  Partial items get proportional
 * rects based on the fraction of characters that are selected.
 *
 * Empty or invalid ranges return an empty array.
 */
export function textRangeToNormalizedRects(
  index: PdfPageTextIndex,
  start: number,
  end: number,
  viewport: PdfViewportInfo,
): NormalizedRect[] {
  if (start >= end || end <= 0) return [];

  const { items, itemCharRanges } = index;
  const pageWidth = viewport.width;
  const pageHeight = viewport.height;

  if (pageWidth <= 0 || pageHeight <= 0) return [];

  const rects: NormalizedRect[] = [];

  for (let i = 0; i < items.length; i++) {
    const range = itemCharRanges[i];
    if (range.start >= end || range.end <= start) continue;

    const item = items[i];
    const str = item.str;
    const strLen = str.length;
    if (strLen === 0) continue;

    // Character offsets within this item
    const itemStart = Math.max(0, start - range.start);
    const itemEnd = Math.min(strLen, end - range.start);

    // Trim leading/trailing whitespace so rects don't extend into nothing
    let effectiveStart = itemStart;
    let effectiveEnd = itemEnd;
    const trimmedStart = str.length - str.trimStart().length;
    const trimmedEnd = str.trimEnd().length;

    if (itemStart === 0) {
      effectiveStart = Math.max(itemStart, trimmedStart);
    }
    if (itemEnd === strLen) {
      effectiveEnd = Math.min(itemEnd, trimmedEnd);
    }
    if (effectiveStart >= effectiveEnd) continue;

    // Fraction of this item that is selected
    const prefixFrac = effectiveStart / strLen;
    const selectedFrac = (effectiveEnd - effectiveStart) / strLen;

    // ---- PDF user‑space rect for this item ----
    // transform = [a, b, c, d, e, f]
    const t = item.transform;
    const scaleX = Math.sqrt(t[0] * t[0] + t[1] * t[1]);
    const scaleY = Math.sqrt(t[2] * t[2] + t[3] * t[3]);

    if (scaleX === 0 || scaleY === 0) continue;

    // pdf.js TextItem width/height are already in page user-space units.
    // The transform describes position/baseline direction; multiplying the
    // width by transform scale again makes highlights far wider than the text.
    const fullW = item.width;
    const fullH = item.height || scaleY;

    // Baseline position
    const baseX = t[4];
    const baseY = t[5];

    // The glyph origin advances along the (t[0], t[1]) direction.
    // For horizontal text this is just the x‑axis.
    const dx = fullW * (scaleX > 0 ? t[0] / scaleX : 0);
    const dy = fullW * (scaleX > 0 ? t[1] / scaleX : 0);

    // Item rect left edge (prefixFrac of the way through the advance).
    // dy tracks the y-component of the advance direction (0 for horizontal text).
    const rectLeft = baseX + prefixFrac * dx;
    const rectWidth = selectedFrac * Math.sqrt(dx * dx + dy * dy);

    // Convert PDF bottom-left coordinates to viewport/SVG top-left coordinates.
    // pdf.js puts horizontal text on a baseline, so use the glyph extent above
    // the baseline as the top edge.
    const rectTop = pageHeight - baseY - fullH;
    const rectH = fullH;

    if (rectWidth <= 0 || rectH <= 0) continue;

    // Normalize to page dimensions
    rects.push({
      x: rectLeft / pageWidth,
      y: rectTop / pageHeight,
      w: rectWidth / pageWidth,
      h: rectH / pageHeight,
    });
  }

  // Merge adjacent rects that are vertically aligned (same y and h, contiguous x)
  return mergeAdjacentRects(rects);
}

// ---------------------------------------------------------------------------
// Full‑item range convenience
// ---------------------------------------------------------------------------

/**
 * Return the normalized rect for a single text item (by index).
 */
export function itemToNormalizedRect(
  index: PdfPageTextIndex,
  itemIndex: number,
  viewport: PdfViewportInfo,
): NormalizedRect | null {
  const range = index.itemCharRanges[itemIndex];
  if (!range) return null;
  const rects = textRangeToNormalizedRects(index, range.start, range.end, viewport);
  return rects.length > 0 ? rects[0] : null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Merge rects that are on the same horizontal line into a single rect.
 */
function mergeAdjacentRects(rects: NormalizedRect[]): NormalizedRect[] {
  if (rects.length < 2) return rects;

  // Sort top‑to‑bottom, then left‑to‑right
  const sorted = [...rects].sort((a, b) => {
    const dy = a.y - b.y;
    if (Math.abs(dy) > 0.0001) return dy;
    return a.x - b.x;
  });

  const merged: NormalizedRect[] = [];
  let current = { ...sorted[0] };

  for (let i = 1; i < sorted.length; i++) {
    const r = sorted[i];
    const maxLineGap = Math.max(0.005, current.h * 4);
    if (
      Math.abs(r.y - current.y) < 0.0001 &&
      Math.abs(r.h - current.h) < 0.0001 &&
      r.x <= current.x + current.w + maxLineGap
    ) {
      // Extend current rect to cover r
      const newRight = Math.max(current.x + current.w, r.x + r.w);
      current.w = newRight - current.x;
    } else {
      merged.push(current);
      current = { ...r };
    }
  }
  merged.push(current);

  return merged;
}
