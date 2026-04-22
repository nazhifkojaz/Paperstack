import { useEffect, useState } from 'react';
import type { Annotation } from '@/api/annotations';
import { useUpdateAnnotation } from '@/api/annotations';
import type { TextLayerHandle } from '@/features/viewer/TextLayer';
import { collectTextNodes, rangeToRects } from '@/features/viewer/pdfTextUtils';
import type { PdfRectData, Rect, TextNode } from '@/features/viewer/pdfTextUtils';

// Re-export types that other modules depend on
export type { Rect, TextNode } from '@/features/viewer/pdfTextUtils';

export interface ResolvedAnnotation extends Annotation {
    _resolved?: boolean;
    _unmatched?: boolean;
}

// ─── Module-level state ──────────────────────────────────────────────────────

/**
 * Tracks annotation IDs that have already been patched to the server.
 * Module-level so all AnnotationOverlay instances share it and don't race.
 * Once patched, the annotation returns from the API with rects.length > 0
 * and is never processed again, so this set only grows during a session.
 */
const _globalPatchedIds = new Set<string>();

/**
 * Tracks annotation IDs that were tried and could not be located in the PDF.
 * Module-level gate: once an annotation is permanently unmatched, we never
 * re-walk the TextLayer DOM for it, preventing the freeze on pages where
 * auto-highlight annotations could not be resolved.
 */
const _globalUnmatchedIds = new Set<string>();

// ─── Hook ────────────────────────────────────────────────────────────────────

/**
 * Resolves auto-highlight annotations that have empty rects by searching
 * for their selected_text in the TextLayer DOM.
 *
 * Strategy:
 *   Tier 1 - exact substring match
 *   Tier 2 - normalized match (Unicode, whitespace, ligatures, bullets)
 *   Tier 3 - longest-common-subsequence word match (configurable threshold)
 *
 * Also tries +/-1 neighboring pages to compensate for LLM page-number errors,
 * but only when no match is found on the assigned page, and with a stricter
 * threshold (0.75 vs 0.6).
 *
 * Annotations that cannot be matched are flagged with _unmatched: true so the
 * sidebar can display them with a "Could not locate in PDF" indicator.
 */
export function useTextMatcher(
    annotations: Annotation[],
    pageNumber: number,
    textLayerHandle: React.RefObject<TextLayerHandle | null> | undefined,
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

        // Annotations assigned to this exact page
        const ownPageAnns = annotations.filter(
            a =>
                a.rects.length === 0 &&
                a.selected_text &&
                a.page_number === pageNumber &&
                !_globalPatchedIds.has(a.id) &&
                !_globalUnmatchedIds.has(a.id),
        );

        // Neighbor annotations (page +/-1) — only tried as fallback with stricter threshold
        const neighborAnns = annotations.filter(
            a =>
                a.rects.length === 0 &&
                a.selected_text &&
                Math.abs(a.page_number - pageNumber) === 1 &&
                !_globalPatchedIds.has(a.id) &&
                !_globalUnmatchedIds.has(a.id),
        );

        if (ownPageAnns.length === 0 && neighborAnns.length === 0) return;

        let cancelled = false;

        handle.renderReady().then(() => {
            if (cancelled) return;

            const containerRect = container.getBoundingClientRect();
            if (containerRect.width === 0 || containerRect.height === 0) return;

            const { textNodes, fullText } = collectTextNodes(container);
            if (fullText.length === 0) return;

            // Get PDF coordinate data for precise rect computation
            const textItems = handle.getTextItems();
            const spanToItemMap = handle.getSpanToItemMap();
            const viewportScale = handle.getViewportScale();
            const pdfData: PdfRectData | undefined =
                textItems.length > 0 && spanToItemMap.size > 0
                    ? { textItems, spanToItemMap, viewportScale }
                    : undefined;

            const newResolved = new Map<string, { rects: Rect[]; page: number }>();
            const newUnmatched = new Set<string>();

            // Pass 1: Own-page annotations with standard threshold (0.6)
            for (const ann of ownPageAnns) {
                if (!ann.selected_text) continue;

                const rects = findTextInDom(
                    textNodes, fullText, ann.selected_text, containerRect, 0.6, pdfData,
                );

                const validRects = rects.filter(r => r.w > 0.001 && r.h > 0.001);
                if (validRects.length === 0) {
                    newUnmatched.add(ann.id);
                    continue;
                }

                newResolved.set(ann.id, { rects: validRects, page: pageNumber });
            }

            // Pass 2: Neighbor annotations with stricter threshold (0.75)
            for (const ann of neighborAnns) {
                if (!ann.selected_text || _globalPatchedIds.has(ann.id)) continue;

                const rects = findTextInDom(
                    textNodes, fullText, ann.selected_text, containerRect, 0.75, pdfData,
                );

                const validRects = rects.filter(r => r.w > 0.001 && r.h > 0.001);
                if (validRects.length === 0) continue;

                newResolved.set(ann.id, { rects: validRects, page: pageNumber });
            }

            // Check cancelled before any mutations or state updates
            if (cancelled) return;

            // Persist resolved annotations to the server
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

            // Gate future effect runs: never re-walk the DOM for permanently unmatched IDs
            for (const id of newUnmatched) {
                _globalUnmatchedIds.add(id);
            }

            // Update unmatched tracking — prune IDs that were resolved
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
    }, [annotations, pageNumber, textLayerHandle, patchAnnotation]);

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

// ─── Text normalization ──────────────────────────────────────────────────────

/**
 * Simple normalization for the search text (needle).
 * Used by Tier 2 to normalize the search query for comparison.
 */
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

/**
 * Build normalized string with a mapping back to original fullText indices.
 *
 * Key difference from the old implementation: we iterate fullText directly
 * (not a pre-NFKC copy) so toOrig always indexes into the original string.
 * Ligature expansion maps the second char to origPos + charLen (the position
 * of the next original character) to avoid zero-length ranges.
 */
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

// ─── Matching ────────────────────────────────────────────────────────────────

/**
 * Core matching function. Returns rects or empty array.
 *
 * @param wordMatchThreshold - minimum fraction of needle words that must
 *   match in-order for Tier 3 (word LCS). Default 0.6 for own-page,
 *   use 0.75 for neighbor-page fallback.
 * @param pdfData - optional PDF coordinate data for precise rect computation
 */
export function findTextInDom(
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

    // Tier 2: Normalized match
    const { norm: normFull, toOrig } = buildNormMap(fullText);
    const normSearch = normalize(searchText);

    const normIdx = normFull.indexOf(normSearch);
    if (normIdx !== -1) {
        const origStart = toOrig[normIdx] ?? 0;
        const normEnd = normIdx + normSearch.length;
        const origEnd = normEnd < toOrig.length ? toOrig[normEnd] : fullText.length;
        return rangeToRects(textNodes, origStart, origEnd, containerRect, pdfData);
    }

    // Tier 3: Word-level LCS match
    const result = wordLcsMatch(normFull, normSearch, toOrig, fullText.length, wordMatchThreshold);
    if (result) {
        return rangeToRects(textNodes, result.start, result.end, containerRect, pdfData);
    }

    return [];
}

/**
 * Word-level longest-common-subsequence matching.
 *
 * 1. Tokenize both needle and haystack into words (with positions).
 * 2. Greedy in-order matching: for each needle word, find next occurrence
 *    in haystack after the previous match.
 * 3. If >= minScore of needle words matched in order, return the haystack span
 *    covering first-to-last matched word.
 * 4. Sanity check: span must be within 50-200% of expected length.
 *
 * @param minScore - minimum fraction of needle words required (default 0.6)
 */
export function wordLcsMatch(
    normFull: string,
    normSearch: string,
    toOrig: number[],
    fullTextLen: number,
    minScore = 0.6,
): { start: number; end: number } | null {
    const haystackWords = tokenize(normFull);
    const needleWords = tokenize(normSearch);

    if (needleWords.length < 3 || haystackWords.length === 0) return null;

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
