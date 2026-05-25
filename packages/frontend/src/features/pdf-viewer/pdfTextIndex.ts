// ---------------------------------------------------------------------------
// pdfTextIndex.ts — Pure text-index builder from pdf.js getTextContent() items
// ---------------------------------------------------------------------------
// All functions are DOM-independent.  No React imports.  No DOM access.
// ---------------------------------------------------------------------------

import type { PdfPageTextIndex, PdfTextItemGeometry } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Text normalization — character-level mapping (ligatures, NFKC, whitespace)
// ---------------------------------------------------------------------------

/**
 * Build a normalized version of `text` together with a mapping
 * `toOrig[i]` = position in `text` for the i‑th character of the output.
 *
 * Normalization steps (in order):
 * 1. Expand fi / fl / ff ligatures before NFKC decomposes them.
 * 2. NFKC‑normalize each code-point.
 * 3. Strip zero‑width / invisible characters.
 * 4. Straighten curly quotes, normalise dashes, unify bullets.
 * 5. Collapse whitespace to a single space.
 *
 * This re‑implements the core logic from the legacy DOM matcher
 * as a pure, DOM‑free utility.
 */
export function buildNormMap(text: string): {
  norm: string;
  toOrig: number[];
} {
  const chars: string[] = [];
  const toOrig: number[] = [];
  let prevSpace = false;
  let i = 0;

  while (i < text.length) {
    const cp = text.codePointAt(i)!;
    const charLen = cp > 0xffff ? 2 : 1;
    const origI = i;
    i += charLen;

    // ---- Ligature expansion (must happen before NFKC) ----
    const origCode = text.charCodeAt(origI);
    if (origCode === 0xfb01) {
      // fi ligature → f + i
      chars.push('f', 'i');
      toOrig.push(origI, origI + charLen);
      prevSpace = false;
      continue;
    }
    if (origCode === 0xfb02) {
      // fl ligature → f + l
      chars.push('f', 'l');
      toOrig.push(origI, origI + charLen);
      prevSpace = false;
      continue;
    }
    if (origCode === 0xfb00) {
      // ff ligature → f + f
      chars.push('f', 'f');
      toOrig.push(origI, origI + charLen);
      prevSpace = false;
      continue;
    }

    // ---- NFKC + zero-width removal ----
    const ch = text.slice(origI, origI + charLen).normalize('NFKC');
    if (/^[\u00ad\u200b\ufeff\u200c\u200d]$/.test(ch)) continue;

    // ---- Quote / dash / bullet normalization ----
    let normalized = ch;
    if (normalized === '\u2018' || normalized === '\u2019') normalized = "'";
    else if (normalized === '\u201c' || normalized === '\u201d') normalized = '"';
    else if (normalized === '\u2013' || normalized === '\u2014') normalized = '-';
    else if (/^[•\u25e6\u25aa\u25b8\u25ba\u2023\u2043\u2219\u00b7]$/.test(normalized))
      normalized = '*';

    if (/^\s+$/.test(normalized)) {
      if (!prevSpace) {
        chars.push(' ');
        toOrig.push(origI);
      }
      prevSpace = true;
    } else {
      for (const outCh of normalized.toLowerCase()) {
        chars.push(outCh);
        toOrig.push(origI);
      }
      prevSpace = false;
    }
  }

  return { norm: chars.join(''), toOrig };
}

// ---------------------------------------------------------------------------
// Dehyphenation — strip line‑break hyphens for search recovery
// ---------------------------------------------------------------------------

/**
 * Strip line‑break hyphens from already‑normalized text.
 *
 * A pattern like "con- sider" becomes "consider".  The returned
 * `toNormal` array maps each output character back to a position
 * in `normalizedText`, so matched spans can be translated back
 * through `toOrig` to the original PDF offsets.
 *
 * Re‑implements legacy dehyphenation as a pure utility.
 */
export function dehyphenate(normalizedText: string): {
  text: string;
  toNormal: number[];
} {
  const chars: string[] = [];
  const toNormal: number[] = [];
  let i = 0;

  while (i < normalizedText.length) {
    const ch = normalizedText[i];

    if (
      ch === '-' &&
      i > 0 &&
      /\w/.test(normalizedText[i - 1])
    ) {
      let j = i + 1;
      while (j < normalizedText.length && /\s/.test(normalizedText[j])) {
        j++;
      }
      if (
        j > i + 1 &&
        j < normalizedText.length &&
        /\w/.test(normalizedText[j])
      ) {
        // Line‑break hyphen found — skip the hyphen and spaces
        i = j;
        continue;
      }
    }

    chars.push(ch);
    toNormal.push(i);
    i++;
  }

  return { text: chars.join(''), toNormal };
}

// ---------------------------------------------------------------------------
// Page text index factory
// ---------------------------------------------------------------------------

/**
 * Build a `PdfPageTextIndex` from the raw items returned by
 * `page.getTextContent()`.
 *
 * The index is the source of truth for offset‑to‑geometry mapping.
 * All fields are derived; nothing is persisted.
 */
export function createPdfPageTextIndex(
  items: PdfTextItemGeometry[],
  pageNumber: number,
): PdfPageTextIndex {
  // Concatenate raw text, injecting a space between items when neither
  // side already has whitespace (prevents word‑fusion across spans).
  const parts: string[] = [];
  const itemCharRanges: Array<{ start: number; end: number }> = [];

  for (const item of items) {
    const prevPart = parts.length > 0 ? parts[parts.length - 1] : null;
    if (
      prevPart !== null &&
      !/\s$/.test(prevPart) &&
      !/^\s/.test(item.str)
    ) {
      parts.push(' ');
    }
    const start = parts.join('').length;
    parts.push(item.str);
    const end = parts.join('').length;
    itemCharRanges.push({ start, end });
  }

  const text = parts.join('');

  // Build normalized version with origin mapping
  const { norm: normalizedText, toOrig: normalizedToOriginal } = buildNormMap(text);

  // Build originalToItem: for each original char position, which item contains it
  const originalToItem: Array<{ itemIndex: number; offset: number }> =
    new Array(text.length);
  let itemIdx = 0;
  for (let i = 0; i < text.length; i++) {
    while (
      itemIdx + 1 < itemCharRanges.length &&
      i >= itemCharRanges[itemIdx].end
    ) {
      itemIdx++;
    }
    originalToItem[i] = {
      itemIndex: itemIdx,
      offset: i - itemCharRanges[itemIdx].start,
    };
  }

  return {
    pageNumber,
    items,
    text,
    normalizedText,
    normalizedToOriginal,
    originalToItem,
    itemCharRanges,
  };
}

// ---------------------------------------------------------------------------
// Convenience: resolve a normalized‑text range back to original offsets
// ---------------------------------------------------------------------------

/**
 * Given start/end offsets in `normalizedText`, return the corresponding
 * range in the raw `text`.  Handles the common patterns:
 *  - direct normalized match
 *  - dehyphenated match (via dehyphenatedToNormal → normalizedToOriginal)
 */
export function normalizedRangeToOriginal(
  index: PdfPageTextIndex,
  normalizedStart: number,
  normalizedEnd: number,
  isDehyphenated = false,
): { start: number; end: number } | null {
  if (normalizedStart >= normalizedEnd) return null;

  const textLen = index.text.length;

  if (isDehyphenated) {
    // Map dehyphenated → normalized → original
    // We need the dehyphenated data — it's stored in the index already,
    // but we compute it inline here for convenience
    const { toNormal } = dehyphenate(index.normalizedText);
    const normStart = toNormal[normalizedStart] ?? 0;
    const normEnd =
      normalizedEnd - 1 < toNormal.length
        ? toNormal[normalizedEnd - 1] + 1
        : index.normalizedText.length;
    const origStart = index.normalizedToOriginal[normStart] ?? 0;
    const origEnd =
      normEnd < index.normalizedToOriginal.length
        ? index.normalizedToOriginal[normEnd]
        : textLen;
    return origEnd > origStart ? { start: origStart, end: origEnd } : null;
  }

  // Direct normalized → original
  // Must be fully within the normalised text bounds
  if (normalizedStart >= index.normalizedToOriginal.length) return null;

  const origStart = index.normalizedToOriginal[normalizedStart] ?? 0;
  const origEnd =
    normalizedEnd < index.normalizedToOriginal.length
      ? index.normalizedToOriginal[normalizedEnd]
      : textLen;
  return origEnd > origStart ? { start: origStart, end: origEnd } : null;
}
