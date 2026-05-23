// ---------------------------------------------------------------------------
// useTextIndexMatcher.ts — Auto‑highlight resolver using page text indexes
// ---------------------------------------------------------------------------
// Replaces the legacy DOM walker with pure text‑index‑based matching.
// ---------------------------------------------------------------------------

import { useEffect, useState } from 'react';
import type { Annotation } from '@/api/annotations';
import { useUpdateAnnotation } from '@/api/annotations';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import { searchTextIndex } from './pdfSearch';
import { textRangeToNormalizedRects } from './pdfGeometry';
import type { Rect } from '@/types/annotation';
import type { HighlightSelectorMetadata, PdfViewportInfo } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Global tracking (module‑level, shared across all pages)
// ---------------------------------------------------------------------------

const _globalPatchedIds = new Set<string>();
const _globalAttemptCounts = new Map<string, number>();
const MAX_ATTEMPTS = 3;

interface ResolvedAnnotation extends Annotation {
  _resolved?: boolean;
  _unmatched?: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Resolve auto‑highlight annotations whose `rects` are empty by searching
 * the page text indexes (built by PdfTextLayer).
 *
 * Matching tiers tried, in order:
 *   exact → normalised → dehyphenated → char‑LCS → word‑LCS
 *
 * Resolved annotations are patched back to the server with computed rects
 * and selector metadata.
 */
export function useTextIndexMatcher(
  annotations: Annotation[],
  pageNumber: number,
  textLayerHandle: React.RefObject<PdfTextLayerHandle | null> | undefined,
  viewport: PdfViewportInfo | null,
  renderId = 0,
): ResolvedAnnotation[] {
  const [resolvedMap, setResolvedMap] = useState<
    Map<string, { rects: Rect[]; page: number }>
  >(new Map());
  const [unmatchedIds, setUnmatchedIds] = useState<Set<string>>(new Set());
  const { mutate: patchAnnotation } = useUpdateAnnotation();

  useEffect(() => {
    if (!textLayerHandle?.current || !viewport) return;

    const handle = textLayerHandle.current;

    // Only annotations that:
    // - have no rects (not yet resolved)
    // - have selected_text to search for
    // - haven't been patched already
    // - still have remaining attempts
    const ownPageAnns = annotations.filter(
      (a) =>
        a.rects.length === 0 &&
        a.selected_text &&
        a.page_number === pageNumber &&
        !_globalPatchedIds.has(a.id) &&
        (_globalAttemptCounts.get(a.id) ?? 0) < MAX_ATTEMPTS,
    );

    const neighborAnns = annotations.filter(
      (a) =>
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

      const index = handle.getTextIndex();
      if (!index) return;

      const newResolved = new Map<
        string,
        { rects: Rect[]; page: number }
      >();
      const newUnmatched = new Set<string>();

      // ---- Resolve own‑page annotations ----
      for (const ann of ownPageAnns) {
        if (!ann.selected_text) continue;

        const match = searchTextIndex(index, ann.selected_text);
        if (!match) {
          newUnmatched.add(ann.id);
          continue;
        }

        const rects = textRangeToNormalizedRects(
          index,
          match.start,
          match.end,
          viewport,
        );

        const validRects = rects.filter(
          (r) => r.w > 0.001 && r.h > 0.001,
        );
        if (validRects.length === 0) {
          newUnmatched.add(ann.id);
          continue;
        }

        newResolved.set(ann.id, { rects: validRects, page: pageNumber });
      }

      // ---- Resolve neighboring‑page annotations (fallback) ----
      for (const ann of neighborAnns) {
        if (!ann.selected_text || _globalPatchedIds.has(ann.id)) continue;

        const match = searchTextIndex(index, ann.selected_text);
        if (!match) continue;

        const rects = textRangeToNormalizedRects(
          index,
          match.start,
          match.end,
          viewport,
        );

        const validRects = rects.filter(
          (r) => r.w > 0.001 && r.h > 0.001,
        );
        if (validRects.length === 0) continue;

        newResolved.set(ann.id, {
          rects: validRects,
          page: pageNumber,
        });
      }

      if (cancelled) return;

      // ---- Patch resolved annotations to server ----
      for (const [annId, entry] of newResolved) {
        if (_globalPatchedIds.has(annId)) continue;
        _globalPatchedIds.add(annId);

        const ann = annotations.find((a) => a.id === annId);
        const metadata: HighlightSelectorMetadata = {
          selector_version: 1,
          text_range: entry.rects.length > 0
            ? {
                page: entry.page,
                start: 0, // we don't know exact offsets from rects
                end: 0,
              }
            : undefined,
          quote: ann?.selected_text
            ? { exact: ann.selected_text, prefix: '', suffix: '' }
            : undefined,
          resolver: { method: 'normalized' },
        };

        // Try to get the actual text range from the match
        const idx = handle.getTextIndex();
        if (idx && ann?.selected_text) {
          const m = searchTextIndex(idx, ann.selected_text);
          if (m) {
            metadata.text_range = {
              page: entry.page,
              start: m.start,
              end: m.end,
            };
            metadata.quote = {
              exact: ann.selected_text,
              prefix: idx.text.slice(Math.max(0, m.start - 40), m.start),
              suffix: idx.text.slice(m.end, Math.min(idx.text.length, m.end + 40)),
            };
            metadata.resolver = { method: m.method, score: m.score };
          }
        }

        const patchData: Partial<Annotation> = {
          rects: entry.rects,
          metadata: metadata as unknown as Record<string, unknown>,
        };
        if (ann && ann.page_number !== entry.page) {
          patchData.page_number = entry.page;
        }
        patchAnnotation({ id: annId, data: patchData });
      }

      // ---- Track unmatched ----
      for (const id of newUnmatched) {
        _globalAttemptCounts.set(
          id,
          (_globalAttemptCounts.get(id) ?? 0) + 1,
        );
      }

      setUnmatchedIds((prev) =>
        new Set(
          [...prev, ...newUnmatched].filter(
            (id) => !newResolved.has(id),
          ),
        ),
      );

      if (newResolved.size > 0) {
        setResolvedMap((prev) => {
          const next = new Map(prev);
          newResolved.forEach((entry, id) => next.set(id, entry));
          return next;
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [
    annotations,
    pageNumber,
    textLayerHandle,
    viewport,
    renderId,
    patchAnnotation,
  ]);

  return annotations.map((ann) => {
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
