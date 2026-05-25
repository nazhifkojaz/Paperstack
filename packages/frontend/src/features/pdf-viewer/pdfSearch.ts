// ---------------------------------------------------------------------------
// pdfSearch.ts — Pure text‑index‑based search for auto‑highlight resolution
// ---------------------------------------------------------------------------
// DOM‑free.  No React.  Uses PdfPageTextIndex from pdfTextIndex.
// ---------------------------------------------------------------------------

import type { PdfPageTextIndex } from './pdfViewerTypes';
import { buildNormMap, dehyphenate } from './pdfTextIndex';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type ResolverMethod =
  | 'exact'
  | 'normalized'
  | 'dehyphenated'
  | 'char-lcs'
  | 'word-lcs';

export interface SearchMatch {
  /** Start offset in the raw page text. */
  start: number;
  /** End offset (exclusive) in the raw page text. */
  end: number;
  /** Which tier produced this match. */
  method: ResolverMethod;
  /** Normalised confidence score (0‑1). */
  score: number;
}

// ---------------------------------------------------------------------------
// Tier helpers (read‑only; carried over conceptually from the legacy matcher)
// ---------------------------------------------------------------------------

/** Exact substring match in raw text. */
function exactMatch(
  text: string,
  needle: string,
): { start: number; end: number } | null {
  const idx = text.indexOf(needle);
  if (idx === -1) return null;
  return { start: idx, end: idx + needle.length };
}

/** Normalised match.  Uses buildNormMap for needle and haystack. */
function normalizedMatch(
  index: PdfPageTextIndex,
  needle: string,
): { start: number; end: number } | null {
  const { norm: normNeedle } = buildNormMap(needle);
  const idx = index.normalizedText.indexOf(normNeedle);
  if (idx === -1) return null;

  const normEnd = idx + normNeedle.length;
  const origStart = index.normalizedToOriginal[idx] ?? 0;
  const origEnd =
    normEnd < index.normalizedToOriginal.length
      ? index.normalizedToOriginal[normEnd]
      : index.text.length;

  if (origEnd <= origStart) return null;
  return { start: origStart, end: origEnd };
}

/** Dehyphenated match — strips line‑break hyphens before comparing. */
function dehyphenatedMatch(
  index: PdfPageTextIndex,
  needle: string,
): { start: number; end: number } | null {
  const { norm: normNeedle } = buildNormMap(needle);
  const { text: dehyphed, toNormal } = dehyphenate(index.normalizedText);

  const idx = dehyphed.indexOf(normNeedle);
  if (idx === -1) return null;

  const dehypEnd = idx + normNeedle.length;
  const normStart = toNormal[idx] ?? 0;
  const normLast = dehypEnd - 1 < toNormal.length
    ? toNormal[dehypEnd - 1]
    : index.normalizedText.length;

  const origStart = index.normalizedToOriginal[normStart] ?? 0;
  const origEnd =
    normLast + 1 < index.normalizedToOriginal.length
      ? index.normalizedToOriginal[normLast + 1]
      : index.text.length;

  if (origEnd <= origStart) return null;
  return { start: origStart, end: origEnd };
}

/** Quote‑prefix/suffix match: extract a phrase and try normalized. */
function quoteMatch(
  index: PdfPageTextIndex,
  needle: string,
): { start: number; end: number } | null {
  // Try matching just the exact quote (shorter phrases are less prone to noise)
  const { norm: normNeedle } = buildNormMap(needle);
  // Split into words and try the longest contiguous run
  const words = normNeedle.split(/\s+/).filter(Boolean);
  if (words.length < 3) return null;

  // Try middle portion (skip first/last word — prefix/suffix may be noisy)
  const core = words.slice(1, -1).join(' ');
  const idx = index.normalizedText.indexOf(core);
  if (idx === -1) return null;

  const normEnd = idx + core.length;
  const origStart = index.normalizedToOriginal[idx] ?? 0;
  const origEnd =
    normEnd < index.normalizedToOriginal.length
      ? index.normalizedToOriginal[normEnd]
      : index.text.length;

  if (origEnd <= origStart) return null;
  return { start: origStart, end: origEnd };
}

// ---------------------------------------------------------------------------
// Char‑level LCS (ported from the legacy matcher)
// ---------------------------------------------------------------------------

function charLcsMatch(
  index: PdfPageTextIndex,
  needle: string,
  minRatio = 0.65,
): { start: number; end: number } | null {
  const { norm: normNeedle } = buildNormMap(needle);
  const haystack = index.normalizedText;
  const m = haystack.length;
  const n = normNeedle.length;
  if (n < 4 || m === 0) return null;

  // Pass 1: compute LCS length with 2‑row DP
  let prev = new Uint16Array(n + 1);
  let curr = new Uint16Array(n + 1);
  for (let i = 1; i <= m; i++) {
    const hch = haystack[i - 1];
    for (let j = 1; j <= n; j++) {
      if (hch === normNeedle[j - 1]) {
        curr[j] = prev[j - 1] + 1;
      } else {
        curr[j] = Math.max(prev[j], curr[j - 1]);
      }
    }
    [prev, curr] = [curr, prev];
  }

  const lcsLen = prev[n];
  if (lcsLen / n < minRatio) return null;

  // Pass 2: full DP with backtracking
  const stride = n + 1;
  const dp = new Uint16Array((m + 1) * stride);
  const dir = new Uint8Array((m + 1) * stride);

  for (let i = 1; i <= m; i++) {
    const rowStart = i * stride;
    const prevRowStart = (i - 1) * stride;
    const hch = haystack[i - 1];
    for (let j = 1; j <= n; j++) {
      if (hch === normNeedle[j - 1]) {
        dp[rowStart + j] = dp[prevRowStart + j - 1] + 1;
        dir[rowStart + j] = 2; // diagonal
      } else if (dp[prevRowStart + j] >= dp[rowStart + j - 1]) {
        dp[rowStart + j] = dp[prevRowStart + j];
        dir[rowStart + j] = 0; // up
      } else {
        dp[rowStart + j] = dp[rowStart + j - 1];
        dir[rowStart + j] = 1; // left
      }
    }
  }

  // Backtrack
  let i = m;
  let j = n;
  let hMin = m;
  let hMax = 0;
  while (i > 0 && j > 0) {
    const d = dir[i * stride + j];
    if (d === 2) {
      hMin = Math.min(hMin, i - 1);
      hMax = Math.max(hMax, i - 1);
      i--;
      j--;
    } else if (d === 0) {
      i--;
    } else {
      j--;
    }
  }

  if (hMin > hMax) return null;

  const normSpanLen = hMax - hMin + 1;
  if (normSpanLen > n * 2.5 || normSpanLen < n * 0.4) return null;

  const origStart = index.normalizedToOriginal[hMin] ?? 0;
  const origEnd =
    hMax + 1 < index.normalizedToOriginal.length
      ? index.normalizedToOriginal[hMax + 1]
      : index.text.length;
  if (origEnd <= origStart) return null;

  return { start: origStart, end: origEnd };
}

// ---------------------------------------------------------------------------
// Word‑level LCS (ported from the legacy matcher)
// ---------------------------------------------------------------------------

function tokenizeText(
  text: string,
): { word: string; start: number; end: number }[] {
  const words: { word: string; start: number; end: number }[] = [];
  const re = /[a-z0-9]+(?:['-][a-z0-9]+)*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    words.push({ word: m[0], start: m.index, end: m.index + m[0].length });
  }
  return words;
}

function wordLcsMatch(
  index: PdfPageTextIndex,
  needle: string,
  minScore = 0.6,
): { start: number; end: number } | null {
  const { norm: normNeedle } = buildNormMap(needle);
  const haystackWords = tokenizeText(index.normalizedText);
  const needleWords = tokenizeText(normNeedle);

  if (needleWords.length < 2 || haystackWords.length === 0) return null;

  const minMatched = Math.ceil(needleWords.length * minScore);

  // Build word → positions map
  const wordPos = new Map<string, number[]>();
  for (let i = 0; i < haystackWords.length; i++) {
    const w = haystackWords[i].word;
    if (!wordPos.has(w)) wordPos.set(w, []);
    wordPos.get(w)!.push(i);
  }

  // Greedy in‑order matching
  let lastIdx = -1;
  const matches: { needleIdx: number; haystackIdx: number }[] = [];
  for (let ni = 0; ni < needleWords.length; ni++) {
    const positions = wordPos.get(needleWords[ni].word);
    if (!positions) continue;
    const nextPos = positions.find((p) => p > lastIdx);
    if (nextPos !== undefined) {
      matches.push({ needleIdx: ni, haystackIdx: nextPos });
      lastIdx = nextPos;
    }
  }

  if (matches.length < minMatched) return null;

  const firstMatch = matches[0];
  const lastMatch = matches[matches.length - 1];
  const hStart = haystackWords[firstMatch.haystackIdx];
  const hEnd = haystackWords[lastMatch.haystackIdx];

  const normSpanLen = hEnd.end - hStart.start;
  const expectedLen = normNeedle.length;
  if (normSpanLen > expectedLen * 2.0 || normSpanLen < expectedLen * 0.5)
    return null;

  const origStart = index.normalizedToOriginal[hStart.start] ?? 0;
  const origEnd =
    hEnd.end < index.normalizedToOriginal.length
      ? index.normalizedToOriginal[hEnd.end]
      : index.text.length;

  if (origEnd <= origStart) return null;
  return { start: origStart, end: origEnd };
}

// ---------------------------------------------------------------------------
// Main search function
// ---------------------------------------------------------------------------

/**
 * Search `needle` (an auto‑highlight `selected_text`) in the page text index.
 * Tries tiers in priority order and returns the first match with a usable score.
 * Returns `null` if no tier produces a match above its minimum threshold.
 */
export function searchTextIndex(
  index: PdfPageTextIndex,
  needle: string,
): SearchMatch | null {
  if (!needle.trim() || index.text.length === 0) return null;

  // Tier 1: Exact raw‑text match
  const exact = exactMatch(index.text, needle);
  if (exact) {
    return { ...exact, method: 'exact', score: 1.0 };
  }

  // Tier 2: Normalised match
  const norm = normalizedMatch(index, needle);
  if (norm) {
    return { ...norm, method: 'normalized', score: 0.95 };
  }

  // Tier 3: Dehyphenated match
  const dehyp = dehyphenatedMatch(index, needle);
  if (dehyp) {
    return { ...dehyp, method: 'dehyphenated', score: 0.9 };
  }

  // Tier 4: Quote prefix/suffix match
  const quote = quoteMatch(index, needle);
  if (quote) {
    return { ...quote, method: 'normalized', score: 0.7 };
  }

  // Tier 5: Char‑level LCS
  const char = charLcsMatch(index, needle);
  if (char) {
    return { ...char, method: 'char-lcs', score: 0.55 };
  }

  // Tier 6: Word‑level LCS
  const word = wordLcsMatch(index, needle);
  if (word) {
    return { ...word, method: 'word-lcs', score: 0.5 };
  }

  return null;
}
