// ---------------------------------------------------------------------------
// pdfViewerTypes.ts — Types for the rewritten PDF viewer
// ---------------------------------------------------------------------------
// Fields marked with @persisted are stored in annotation metadata (JSONB).
// Fields marked with @derived are computed at runtime and never persisted.
// Fields marked with @runtime are viewer UI state, not persisted to the server.
// ---------------------------------------------------------------------------

import type { Rect } from '@/types/annotation';

// ---------------------------------------------------------------------------
// PDF text item — extracted from page.getTextContent()
// ---------------------------------------------------------------------------

/** One text item from pdf.js TextContent, with geometry resolved from its transform.
 *  Mirrors pdfjs-dist's TextItem but kept as our own type so utilities don't
 *  import pdfjs-dist directly. */
export interface PdfTextItemGeometry {
  /** The raw text string (may contain ligatures, hyphens, etc.). */
  str: string;
  /** Item width in PDF user-space units. */
  width: number;
  /** Item height in PDF user-space units. */
  height: number;
  /** The 6-element pdf.js transform array [a, b, c, d, e, f]. */
  transform: number[];
}

// ---------------------------------------------------------------------------
// Page text index — the source of truth for text offset ↔ geometry mapping
// ---------------------------------------------------------------------------

/**
 * Full text index built from page.getTextContent() for one page.
 * All properties are @derived — computed from PDF content stream, never persisted.
 */
export interface PdfPageTextIndex {
  /** 1-based page number. */
  pageNumber: number;
  /** Every text item, in original reading order. */
  items: PdfTextItemGeometry[];
  /** Concatenated raw text of all items (may include ligatures/hyphens). */
  text: string;
  /** text with whitespace, quotes, dashes normalized for search/matching. */
  normalizedText: string;
  /** normalizedToOriginal[i] = index in `text` for the i-th char of normalizedText.
   *  Length equals normalizedText.length. */
  normalizedToOriginal: number[];
  /** originalToItem[originalOffset] = { itemIndex, offset }.
   *  Length equals text.length. */
  originalToItem: Array<{ itemIndex: number; offset: number }>;
  /** itemCharRanges[i] = { start, end } in `text` for items[i]. */
  itemCharRanges: Array<{ start: number; end: number }>;
}

// ---------------------------------------------------------------------------
// PDF geometry — viewport-relative rects
// ---------------------------------------------------------------------------

/** A rect in page-normalized coordinates (0..1 for x/w, 0..pageHeight/pageWidth for y/h). */
export type NormalizedRect = Rect;

/** Viewport descriptor needed by geometry utilities. */
export interface PdfViewportInfo {
  width: number;
  height: number;
  rotation: number;
  scale: number;
}

// ---------------------------------------------------------------------------
// Annotation selector metadata (@persisted in annotation.metadata)
// ---------------------------------------------------------------------------

/**
 * Stored inside annotation.metadata for highlights created by the new viewer.
 * All fields are @persisted (JSONB).
 *
 * Rules:
 * - `rects` on the annotation are always populated for rendering/export compat.
 * - `text_range` is the preferred source for future re-rendering.
 * - `quote` is a recovery fallback when indexes drift.
 */
export interface HighlightSelectorMetadata {
  /** Version discriminator. Currently 1. */
  selector_version: 1;
  /** Page-level text offsets in the page text index. @persisted */
  text_range?: {
    page: number;
    start: number;
    end: number;
  };
  /** Quote context for recovery/verification. @persisted */
  quote?: {
    exact: string;
    prefix: string;
    suffix: string;
  };
  /** Resolver info for debugging auto-highlight. @persisted */
  resolver?: {
    method: 'selection' | 'exact' | 'normalized' | 'dehyphenated' | 'fuzzy' | 'char-lcs' | 'word-lcs';
    score?: number;
  };
}

// ---------------------------------------------------------------------------
// Viewer UI state (@runtime only, not persisted to the server)
// ---------------------------------------------------------------------------

export type PdfViewerZoomMode = 'manual' | 'fit-width' | 'fit-page';

export type PdfViewerRotation = 0 | 90 | 180 | 270;

/**
 * Core viewer state.
 *
 * Important design rule:
 * - `visiblePage` is updated passively by IntersectionObserver during scrolling.
 * - `targetPage` is set by explicit navigation actions (toolbar, chat citation, sidebar).
 * - Only `targetPage` triggers scrollIntoView.  `visiblePage` MUST NOT cause scrolling.
 */
export interface PdfViewerState {
  /** Page most visible in the viewport (@runtime). */
  visiblePage: number;
  /** Page the user explicitly wants to see, or null after the jump completes (@runtime). */
  targetPage: number | null;
  /** Total page count from the loaded document (@runtime). */
  totalPages: number;
  /** Current zoom factor (1 = page width = container width at scale=1). */
  zoom: number;
  /** Zoom interaction mode. */
  zoomMode: PdfViewerZoomMode;
  /** Visual rotation of every page. */
  rotation: PdfViewerRotation;
}

// ---------------------------------------------------------------------------
// PDF document source — passed in from the host page
// ---------------------------------------------------------------------------

export type PdfSource =
  | { type: 'github'; sha: string; filename: string }
  | { type: 'drive'; fileId: string; filename: string }
  | { type: 'upload'; pdfId: string };
