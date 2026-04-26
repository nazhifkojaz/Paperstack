import { useEffect, useState } from 'react';
import type { Annotation } from '@/api/annotations';
import { useUpdateAnnotation } from '@/api/annotations';
import type { TextLayerHandle } from '@/types/viewer';
import type { PdfRectData, TextNode } from '@/types/viewer';
import type { Rect } from '@/types/annotation';
import { collectTextNodes, rangeToRects } from '@/lib/pdfTextUtils';

/**
 * Tracks annotation IDs that have already been patched to the server.
 * Module-level so all AnnotationOverlay instances share it and don't race.
 * Once patched, the annotation returns from the API with rects.length > 0
 * and is never processed again, so this set only grows during a session.
 */
const _globalPatchedIds = new Set<string>();

/**
 * Tracks how many times each annotation ID was tried and not found.
 * Annotations get up to MAX_ATTEMPTS retries before being permanently
 * skipped, preventing infinite DOM walks for genuinely unmatchable text
 * while allowing transient failures (page not yet scrolled, text layer
 * not ready) to succeed on a later render cycle.
 */
const _globalAttemptCounts = new Map<string, number>();
const MAX_ATTEMPTS = 3;

interface PageTextCache {
    fullText: string;
    normFull: string;
    toOrig: number[];
    tokens: { word: string; start: number; end: number }[];
    dehyphenated: { text: string; toNormal: number[] };
}

const _pageTextCache = new WeakMap<Element, PageTextCache>();

function getOrCreatePageCache(container: Element, fullText: string): PageTextCache {
    const existing = _pageTextCache.get(container);
    if (existing && existing.fullText === fullText) return existing;

    const { norm: normFull, toOrig } = buildNormMap(fullText);
    const tokens = tokenize(normFull);
    const dehyphenated = dehyphenate(normFull);

    const cache: PageTextCache = { fullText, normFull, toOrig, tokens, dehyphenated };
    _pageTextCache.set(container, cache);
    return cache;
}

interface ResolvedAnnotation extends Annotation {
    _resolved?: boolean;
    _unmatched?: boolean;
}

/** Resolves auto-highlight annotations with empty rects by searching TextLayer DOM. Tries exact, normalized, and word-LCS matches. */
export function useTextMatcher(
    annotations: Annotation[],
    pageNumber: number,
    textLayerHandle: React.RefObject<TextLayerHandle | null> | undefined,
    renderId = 0,
): ResolvedAnnotation[] {
    const [resolvedMap, setResolvedMap] = useState<
        Map<string, { rects: Rect[]; page: number }>
    >(new Map());
    const [unmatchedIds, setUnmatchedIds] = useState<Set<string>>(new Set());
    const { mutate: patchAnnotation } = useUpdateAnnotation();

    useEffect(() => {
        if (!textLayerHandle?.current) return;
        const handle = textLayerHandle.current;
        const container = handle.getContainer();
        if (!container) return;


        const ownPageAnns = annotations.filter(
            a =>
                a.rects.length === 0 &&
                a.selected_text &&
                a.page_number === pageNumber &&
                !_globalPatchedIds.has(a.id) &&
                (_globalAttemptCounts.get(a.id) ?? 0) < MAX_ATTEMPTS,
        );


        const neighborAnns = annotations.filter(
            a =>
                a.rects.length === 0 &&
                a.selected_text &&
                Math.abs(a.page_number - pageNumber) <= 2 &&
                !_globalPatchedIds.has(a.id) &&
                (_globalAttemptCounts.get(a.id) ?? 0) < MAX_ATTEMPTS,
        );

        if (ownPageAnns.length === 0 && neighborAnns.length === 0) return;

        let cancelled = false;

        handle.renderReady().then(() => {
            if (cancelled) return;

            const containerRect = container.getBoundingClientRect();
            if (containerRect.width === 0 || containerRect.height === 0) return;

            const { textNodes, fullText } = collectTextNodes(container);
            if (fullText.length === 0) return;


            const textItems = handle.getTextItems();
            const spanToItemMap = handle.getSpanToItemMap();
            const viewportScale = handle.getViewportScale();
            const pdfData: PdfRectData | undefined =
                textItems.length > 0 && spanToItemMap.size > 0
                    ? { textItems, spanToItemMap, viewportScale }
                    : undefined;

            const newResolved = new Map<string, { rects: Rect[]; page: number }>();
            const newUnmatched = new Set<string>();


            for (const ann of ownPageAnns) {
                if (!ann.selected_text) continue;

                const rects = findTextInDom(
                    container, textNodes, fullText, ann.selected_text, containerRect, 0.6, pdfData,
                );

                const validRects = rects.filter(r => r.w > 0.001 && r.h > 0.001);
                if (validRects.length === 0) {
                    if (fullText.length > 0) {
                        newUnmatched.add(ann.id);
                    }
                    continue;
                }

                newResolved.set(ann.id, { rects: validRects, page: pageNumber });
            }


            for (const ann of neighborAnns) {
                if (!ann.selected_text || _globalPatchedIds.has(ann.id)) continue;

                const rects = findTextInDom(
                    container, textNodes, fullText, ann.selected_text, containerRect, 0.75, pdfData,
                );

                const validRects = rects.filter(r => r.w > 0.001 && r.h > 0.001);
                if (validRects.length === 0) {
                    if (fullText.length > 0) {
                        // neighbor fallback failed but page IS loaded; don't blacklist here
                        // (the annotation's own page handler will handle it)
                    }
                    continue;
                }

                newResolved.set(ann.id, { rects: validRects, page: pageNumber });
            }


            if (cancelled) return;


            for (const [annId, entry] of newResolved) {
                if (_globalPatchedIds.has(annId)) continue;
                _globalPatchedIds.add(annId);

                const ann = annotations.find(a => a.id === annId);
                const patchData: Partial<Annotation> = { rects: entry.rects };
                if (ann && ann.page_number !== entry.page) {
                    patchData.page_number = entry.page;
                }
                patchAnnotation({ id: annId, data: patchData });
            }


            for (const id of newUnmatched) {
                _globalAttemptCounts.set(id, (_globalAttemptCounts.get(id) ?? 0) + 1);
            }


            setUnmatchedIds(prev => new Set(
                [...prev, ...newUnmatched]
                    .filter(id => !newResolved.has(id)),
            ));

            if (newResolved.size > 0) {
                setResolvedMap(prev => {
                    const next = new Map(prev);
                    newResolved.forEach((entry, id) => next.set(id, entry));
                    return next;
                });
            }
        });

        return () => { cancelled = true; };
    }, [annotations, pageNumber, textLayerHandle, renderId, patchAnnotation]);

    return annotations.map(ann => {
        if (ann.rects.length > 0) return ann;
        const resolved = resolvedMap.get(ann.id);
        if (resolved) {
            return {
                ...ann,
                rects: resolved.rects,
                page_number: resolved.page,
                _resolved: true,
            };
        }
        if (unmatchedIds.has(ann.id)) {
            return { ...ann, _unmatched: true };
        }
        return ann;
    });
}

/** Normalize text for search: NFKC, whitespace, ligatures, bullets. */
export function normalize(text: string): string {
    return text
        .normalize('NFKC')
        .replace(/[\u00AD\u200B\uFEFF\u200C\u200D]/g, '')
        .replace(/['\u2018\u2019]/g, "'")
        .replace(/["\u201C\u201D]/g, '"')
        .replace(/[\u2013\u2014]/g, '-')
        .replace(/[•\u25E6\u25AA\u25B8\u25BA\u2023\u2043\u2219\u00B7]/g, '*')
        .replace(/\ufb01/g, 'fi')
        .replace(/\ufb02/g, 'fl')
        .replace(/\ufb00/g, 'ff')
        .replace(/\s+/g, ' ')
        .trim()
        .toLowerCase();
}

/** Build normalized string with mapping back to original indices for ligature handling. */
export function buildNormMap(fullText: string): { norm: string; toOrig: number[] } {
    const chars: string[] = [];
    const toOrig: number[] = [];
    let prevSpace = false;
    let i = 0;

    while (i < fullText.length) {
        const cp = fullText.codePointAt(i)!;
        const charLen = cp > 0xFFFF ? 2 : 1;
        const origI = i;
        i += charLen;

        // Check for ligatures first — they must be handled before NFKC
        // normalization, which would decompose them and lose the original
        // char boundary information needed for correct toOrig mapping.
        const origCode = fullText.charCodeAt(origI);
        if (origCode === 0xFB01) { // fi ligature
            chars.push('f', 'i');
            toOrig.push(origI, origI + charLen);
            prevSpace = false;
            continue;
        }
        if (origCode === 0xFB02) { // fl ligature
            chars.push('f', 'l');
            toOrig.push(origI, origI + charLen);
            prevSpace = false;
            continue;
        }
        if (origCode === 0xFB00) { // ff ligature
            chars.push('f', 'f');
            toOrig.push(origI, origI + charLen);
            prevSpace = false;
            continue;
        }

        // Normalize single character via NFKC
        const ch = fullText.slice(origI, origI + charLen).normalize('NFKC');

        // Skip zero-width / invisible characters
        if (/^[\u00AD\u200B\uFEFF\u200C\u200D]$/.test(ch)) continue;

        // Quote and dash normalization
        let normalized = ch;
        if (normalized === '\u2018' || normalized === '\u2019') normalized = "'";
        else if (normalized === '\u201C' || normalized === '\u201D') normalized = '"';
        else if (normalized === '\u2013' || normalized === '\u2014') normalized = '-';
        else if (/^[•\u25E6\u25AA\u25B8\u25BA\u2023\u2043\u2219\u00B7]$/.test(normalized)) normalized = '*';

        if (/^\s+$/.test(normalized)) {
            if (!prevSpace) {
                chars.push(' ');
                toOrig.push(origI);
            }
            prevSpace = true;
        } else {
            // NFKC may expand a single char to multiple (e.g. compatibility chars).
            // Emit each output char mapping back to the same original position.
            for (const outCh of normalized.toLowerCase()) {
                chars.push(outCh);
                toOrig.push(origI);
            }
            prevSpace = false;
        }
    }

    return { norm: chars.join(''), toOrig };
}

/** Strip line-break hyphens from normalized text, producing a version where
 *  hyphenated words (e.g. "con- sider") become continuous ("consider").
 *  Builds a mapping back to positions in the input normalized string so
 *  matched spans can be translated to original PDF coordinates. */
export function dehyphenate(normalizedText: string): { text: string; toNormal: number[] } {
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

/** Split text into sentences on punctuation boundaries. */
export function splitSentences(text: string): string[] {
    const splitRe = /(?<=[.!?])\s+(?=[A-Z])/g
    const trimmed = text.trim()
    const parts = trimmed.split(splitRe)
    return parts.filter(s => s.length > 0)
}

/** Core matching: exact → normalized → dehyphenated → sentence-level → word-LCS. Returns rects or empty array. */
function findTextInDom(
    container: Element,
    textNodes: TextNode[],
    fullText: string,
    searchText: string,
    containerRect: DOMRect,
    wordMatchThreshold = 0.6,
    pdfData?: PdfRectData,
): Rect[] {
    // Tier 1: Exact match
    const exactIdx = fullText.indexOf(searchText);
    if (exactIdx !== -1) {
        return rangeToRects(textNodes, exactIdx, exactIdx + searchText.length, containerRect, pdfData);
    }

    const cache = getOrCreatePageCache(container, fullText);
    const normSearch = normalize(searchText);

    // Tier 2: Normalized match
    const normIdx = cache.normFull.indexOf(normSearch);
    if (normIdx !== -1) {
        const origStart = cache.toOrig[normIdx] ?? 0;
        const normEnd = normIdx + normSearch.length;
        const origEnd = normEnd < cache.toOrig.length ? cache.toOrig[normEnd] : fullText.length;
        return rangeToRects(textNodes, origStart, origEnd, containerRect, pdfData);
    }

    // Tier 2.5: Dehyphenated match (handles line-break hyphenation)
    const dehypIdx = cache.dehyphenated.text.indexOf(normSearch);
    if (dehypIdx !== -1) {
        const dehypEnd = dehypIdx + normSearch.length;
        const normStartPos = cache.dehyphenated.toNormal[dehypIdx] ?? 0;
        const normLastChar = cache.dehyphenated.toNormal[dehypEnd - 1] ?? 0;
        const origStart = cache.toOrig[normStartPos] ?? 0;
        const origEnd = normLastChar + 1 < cache.toOrig.length
            ? cache.toOrig[normLastChar + 1]
            : fullText.length;
        return rangeToRects(textNodes, origStart, origEnd, containerRect, pdfData);
    }

    // Tier 2.75: Sentence-level match (handles text fragmented by
    // column-extraction reordering in double-column PDFs). Each sentence
    // is searched independently; combined span covers the best run.
    const sentences = splitSentences(normSearch);
    if (sentences.length >= 2) {
        const positions: { start: number; end: number }[] = [];
        for (const sent of sentences) {
            const idx = cache.normFull.indexOf(sent);
            if (idx !== -1) {
                positions.push({ start: idx, end: idx + sent.length });
            }
        }
        const minSentences = Math.max(1, Math.floor(sentences.length * 0.5));
        if (positions.length >= minSentences) {
            positions.sort((a, b) => a.start - b.start);
            const spanStart = cache.toOrig[positions[0].start] ?? 0;
            const lastEnd = positions[positions.length - 1].end;
            const spanEnd = lastEnd < cache.toOrig.length
                ? cache.toOrig[lastEnd]
                : fullText.length;
            if (spanEnd > spanStart) {
                return rangeToRects(textNodes, spanStart, spanEnd, containerRect, pdfData);
            }
        }
    }

    // Tier 2.85: Character-level LCS (handles formulas, special unicode,
    // and PyMuPDF vs PDF.js text-extraction divergence). More precise than
    // word-LCS — characters must match in-order at >=65% rate.
    const charResult = charLcsMatch(cache.normFull, normSearch, cache.toOrig, fullText.length);
    if (charResult) {
        return rangeToRects(textNodes, charResult.start, charResult.end, containerRect, pdfData);
    }

    // Tier 3: Word-level LCS match
    const result = wordLcsMatch(cache.normFull, normSearch, cache.toOrig, fullText.length, wordMatchThreshold, cache.tokens);
    if (result) {
        return rangeToRects(textNodes, result.start, result.end, containerRect, pdfData);
    }

    return [];
}

/** Character-level LCS matching: finds the longest common subsequence
 *  between search and haystack strings, then backtracks to determine the
 *  span in the haystack. Accepts if >=65% of needle chars match in-order.
 *  Handles formulas, special unicode, and text-extraction divergence. */
export function charLcsMatch(
    haystack: string,
    needle: string,
    toOrig: number[],
    fullTextLen: number,
    minRatio = 0.65,
): { start: number; end: number } | null {
    const m = haystack.length
    const n = needle.length
    if (n < 4 || m === 0) return null

    // Pass 1: compute LCS length with 2-row DP (O(m·n) time, O(n) space)
    let prev = new Uint16Array(n + 1)
    let curr = new Uint16Array(n + 1)
    for (let i = 1; i <= m; i++) {
        const hch = haystack[i - 1]
        for (let j = 1; j <= n; j++) {
            if (hch === needle[j - 1]) {
                curr[j] = prev[j - 1] + 1
            } else {
                curr[j] = Math.max(prev[j], curr[j - 1])
            }
        }
        ;[prev, curr] = [curr, prev]
    }

    const lcsLen = prev[n]
    if (lcsLen / n < minRatio) return null

    // Pass 2: full DP with direction trace for backtracking
    const stride = n + 1
    const dp = new Uint16Array((m + 1) * stride)
    const dir = new Uint8Array((m + 1) * stride) // 0=up, 1=left, 2=diag

    for (let i = 1; i <= m; i++) {
        const rowStart = i * stride
        const prevRowStart = (i - 1) * stride
        const hch = haystack[i - 1]
        for (let j = 1; j <= n; j++) {
            if (hch === needle[j - 1]) {
                dp[rowStart + j] = dp[prevRowStart + j - 1] + 1
                dir[rowStart + j] = 2
            } else if (dp[prevRowStart + j] >= dp[rowStart + j - 1]) {
                dp[rowStart + j] = dp[prevRowStart + j]
                dir[rowStart + j] = 0
            } else {
                dp[rowStart + j] = dp[rowStart + j - 1]
                dir[rowStart + j] = 1
            }
        }
    }

    // Backtrack to find span in haystack
    let i = m
    let j = n
    let hMin = m
    let hMax = 0
    while (i > 0 && j > 0) {
        const d = dir[i * stride + j]
        if (d === 2) {
            hMin = Math.min(hMin, i - 1)
            hMax = Math.max(hMax, i - 1)
            i--
            j--
        } else if (d === 0) {
            i--
        } else {
            j--
        }
    }

    if (hMin > hMax) return null

    const origStart = toOrig[hMin] ?? 0
    const origEnd = hMax + 1 < toOrig.length ? toOrig[hMax + 1] : fullTextLen
    if (origEnd <= origStart) return null

    // Reject wildly disproportionate spans (same guard as wordLcsMatch)
    const normSpanLen = hMax - hMin + 1
    if (normSpanLen > n * 2.5 || normSpanLen < n * 0.4) return null

    return { start: origStart, end: origEnd }
}

/** Word-level LCS matching with greedy in-order algorithm. Returns span or null. */
export function wordLcsMatch(
    normFull: string,
    normSearch: string,
    toOrig: number[],
    fullTextLen: number,
    minScore = 0.6,
    haystackTokens?: { word: string; start: number; end: number }[],
): { start: number; end: number } | null {
    const haystackWords = haystackTokens ?? tokenize(normFull);
    const needleWords = tokenize(normSearch);

    if (needleWords.length < 2 || haystackWords.length === 0) return null;

    const minMatched = Math.ceil(needleWords.length * minScore);

    // Build word -> haystack indices map
    const wordPositions = new Map<string, number[]>();
    for (let i = 0; i < haystackWords.length; i++) {
        const w = haystackWords[i].word;
        if (!wordPositions.has(w)) wordPositions.set(w, []);
        wordPositions.get(w)!.push(i);
    }

    // Greedy in-order matching
    let lastIdx = -1;
    const matches: { needleIdx: number; haystackIdx: number }[] = [];

    for (let ni = 0; ni < needleWords.length; ni++) {
        const positions = wordPositions.get(needleWords[ni].word);
        if (!positions) continue;

        const nextPos = positions.find(p => p > lastIdx);
        if (nextPos !== undefined) {
            matches.push({ needleIdx: ni, haystackIdx: nextPos });
            lastIdx = nextPos;
        }
    }

    if (matches.length < minMatched) return null;

    // Compute span in haystack
    const firstMatch = matches[0];
    const lastMatch = matches[matches.length - 1];
    const hStart = haystackWords[firstMatch.haystackIdx];
    const hEnd = haystackWords[lastMatch.haystackIdx];

    // Map back to original positions via toOrig
    const origStart = toOrig[hStart.start] ?? 0;
    // hEnd.end is the exclusive end in normFull. toOrig[hEnd.end] gives the
    // original position of the char right after the last matched word.
    const origEnd = hEnd.end < toOrig.length ? toOrig[hEnd.end] : fullTextLen;

    // Sanity: span shouldn't be wildly different from expected length.
    // Compare in normalized units to avoid false rejections from whitespace
    // differences between original and normalized text.
    const normSpanLen = hEnd.end - hStart.start;
    const expectedLen = normSearch.length;
    if (normSpanLen > expectedLen * 2.0 || normSpanLen < expectedLen * 0.5) return null;

    return { start: origStart, end: origEnd };
}

/** Tokenize into words with positions in the normalized string. */
export function tokenize(text: string): { word: string; start: number; end: number }[] {
    const words: { word: string; start: number; end: number }[] = [];
    const regex = /[a-z0-9]+(?:['-][a-z0-9]+)*/g;
    let m: RegExpExecArray | null;
    while ((m = regex.exec(text)) !== null) {
        words.push({ word: m[0], start: m.index, end: m.index + m[0].length });
    }
    return words;
}
