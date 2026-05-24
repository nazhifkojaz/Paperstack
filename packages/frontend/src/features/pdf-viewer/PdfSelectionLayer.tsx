import { useState, useEffect, useCallback } from 'react';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import {
  getRotatedViewportSize,
  projectNormalizedRectsForRotation,
  textRangeToNormalizedRects,
  unprojectNormalizedRectsForRotation,
} from './pdfGeometry';
import { searchTextIndex } from './pdfSearch';
import { useNewPdfViewerStore } from './pdfViewerStore';
import { SelectionPopup } from '@/features/annotations/SelectionPopup';
import type { HighlightSelectorMetadata, PdfPageTextIndex, PdfViewportInfo } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PdfSelectionLayerProps {
  textLayerRef: React.RefObject<PdfTextLayerHandle | null>;
  pageNumber: number;
}

interface SelectionState {
  selectionRect: { x: number; y: number; width: number; height: number };
  displayRects: Array<{ x: number; y: number; w: number; h: number }>;
  normalizedRects: Array<{ x: number; y: number; w: number; h: number }>;
  selectedText: string;
  metadata: HighlightSelectorMetadata;
}

// ---------------------------------------------------------------------------
// DOM‑walker: builds fullText + character‑range mapping for <Text> nodes
// ---------------------------------------------------------------------------

interface DomTextNode {
  node: Text;
  start: number; // character position in fullText
  end: number;
}

function collectDomTextNodes(container: HTMLElement): {
  textNodes: DomTextNode[];
  fullText: string;
} {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const nodes: DomTextNode[] = [];
  let full = '';
  let prevParent: Node | null = null;

  let node: Text | null;
  while ((node = walker.nextNode() as Text | null)) {
    const parent = node.parentNode;
    const content = node.textContent || '';

    // Inject space when crossing span boundaries to match how
    // createPdfPageTextIndex builds the raw text.
    if (
      prevParent !== null &&
      parent !== prevParent &&
      full.length > 0 &&
      !/\s$/.test(full) &&
      !/^\s/.test(content)
    ) {
      full += ' ';
    }

    const start = full.length;
    full += content;
    nodes.push({ node, start, end: full.length });
    prevParent = parent;
  }

  return { textNodes: nodes, fullText: full };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Listens for mouseup on the text layer container and converts the
 * browser DOM selection into text‑range offsets, normalized rects,
 * and selector metadata.  Then shows the SelectionPopup.
 */
export const PdfSelectionLayer = ({
  textLayerRef,
  pageNumber,
}: PdfSelectionLayerProps) => {
  const [selection, setSelection] = useState<SelectionState | null>(null);

  const zoom = useNewPdfViewerStore((s) => s.zoom);
  const rotation = useNewPdfViewerStore((s) => s.rotation);
  const dimensions = useNewPdfViewerStore((s) =>
    s.pageDimensions.get(pageNumber),
  );

  const handleDismiss = useCallback(() => setSelection(null), []);

  // ---- Attach mouseup listener to the text layer container ----
  useEffect(() => {
    const handle = textLayerRef?.current;
    if (!handle) return;

    const container = handle.getContainer();
    if (!container) return;

    const onMouseUp = () => {
      // Small delay so the browser has time to finalise the selection
      setTimeout(() => {
        processSelection(
          handle,
          container,
          pageNumber,
          zoom,
          rotation,
          dimensions ? { baseWidth: dimensions.baseWidth, baseHeight: dimensions.baseHeight } : null,
          setSelection,
        );
      }, 10);
    };

    document.addEventListener('mouseup', onMouseUp);
    return () => document.removeEventListener('mouseup', onMouseUp);
  }, [textLayerRef, pageNumber, zoom, rotation, dimensions, handleDismiss]);

  if (!selection) return null;

  // Viewport pixel dimensions for SVG
  const viewport = dimensions
    ? {
        width: dimensions.baseWidth,
        height: dimensions.baseHeight,
        rotation,
        scale: zoom,
      }
    : null;
  const { width: vpW, height: vpH } = viewport
    ? getRotatedViewportSize(viewport)
    : { width: 612, height: 792 };

  return (
    <>
      {/* SVG highlight overlay — replaces the cleared native selection visual */}
      <svg
        className="absolute inset-0 pointer-events-none z-25"
        style={{ width: `${vpW}px`, height: `${vpH}px` }}
        aria-hidden
      >
        {selection.displayRects.map((r, i) => (
          <rect
            key={i}
            x={r.x * vpW}
            y={r.y * vpH}
            width={r.w * vpW}
            height={r.h * vpH}
            rx={2}
            ry={2}
            fill="rgba(100, 160, 255, 0.4)"
          />
        ))}
      </svg>
      <SelectionPopup
        selectionRect={selection.selectionRect}
        normalizedRects={selection.normalizedRects}
        selectedText={selection.selectedText}
        pageNumber={pageNumber}
        onDismiss={handleDismiss}
        metadata={selection.metadata as unknown as Record<string, unknown>}
      />
    </>
  );
};

// ---------------------------------------------------------------------------
// Core selection processing
// ---------------------------------------------------------------------------

function processSelection(
  handle: PdfTextLayerHandle,
  container: HTMLDivElement,
  pageNumber: number,
  zoom: number,
  rotation: number,
  pageDims: { baseWidth: number; baseHeight: number } | null,
  setResult: (s: SelectionState | null) => void,
) {
  // 1. Get the browser selection
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || !container.contains(sel.anchorNode)) {
    setResult(null);
    return;
  }

  const range = sel.getRangeAt(0);
  const rawText = range.toString();
  if (!rawText.trim()) {
    setResult(null);
    return;
  }

  // 2. Validate single‑page selection
  if (!isSelectionWithinElement(container, sel)) {
    setResult(null);
    return;
  }

  // 3. Map DOM Range start/end → character positions in the PDF text index.
  // Prefer pdf.js span mappings over a raw DOM walk: the browser text layer can
  // split/wrap text differently at high zoom, but each span still points back to
  // a stable PDF text item.
  const index = handle.getTextIndex();
  let matchStart = -1;
  let matchEnd = -1;
  let fullText = index?.text ?? '';

  if (index) {
    const offsets = resolveRangeOffsetsFromTextIndex(
      range,
      container,
      handle.getSpanToItemMap(),
      index,
    );
    if (offsets) {
      matchStart = offsets.start;
      matchEnd = offsets.end;
    }
  }

  if ((matchStart === -1 || matchEnd === -1) && index) {
    const textMatch = searchTextIndex(index, rawText);
    if (textMatch) {
      matchStart = textMatch.start;
      matchEnd = textMatch.end;
      fullText = index.text;
    }
  }

  // Fallback for unusual browser Range boundaries that don't resolve to a
  // mapped pdf.js span.
  if (matchStart === -1 || matchEnd === -1) {
    matchStart = -1;
    matchEnd = -1;
    const domText = collectDomTextNodes(container);
    fullText = domText.fullText;
    if (fullText.length === 0) return;

    for (const tn of domText.textNodes) {
      if (matchStart === -1 && tn.node === range.startContainer) {
        matchStart = tn.start + range.startOffset;
      }
      if (matchEnd === -1 && tn.node === range.endContainer) {
        matchEnd = tn.start + range.endOffset;
      }
      if (matchStart !== -1 && matchEnd !== -1) break;
    }
  }

  if (matchStart === -1 || matchEnd === -1 || matchStart >= matchEnd) {
    setResult(null);
    return;
  }

  // 4. Compute normalized rects. For the live user selection, browser range
  // rects are more precise than PDF text-item projection, especially for
  // partial words and high zoom. The text range is still stored in metadata.
  let displayRects = getDomSelectionRects(range, container);
  let normalizedRects =
    displayRects.length > 0
      ? unprojectNormalizedRectsForRotation(displayRects, rotation)
      : [];

  if (displayRects.length === 0 && index && pageDims) {
    const canonicalViewport: PdfViewportInfo = {
      width: pageDims.baseWidth,
      height: pageDims.baseHeight,
      rotation: 0,
      scale: zoom,
    };
    normalizedRects = textRangeToNormalizedRects(
      index,
      matchStart,
      matchEnd,
      canonicalViewport,
    );
    displayRects = projectNormalizedRectsForRotation(
      normalizedRects,
      rotation,
    );
  }

  if (normalizedRects.length === 0 || displayRects.length === 0) {
    setResult(null);
    return;
  }

  // 6. Build selection rect for popup positioning (screen coords)
  const rangeBounds = range.getBoundingClientRect();
  const selectionRect = {
    x: rangeBounds.left,
    y: rangeBounds.top,
    width: rangeBounds.width,
    height: rangeBounds.height,
  };

  // 7. Build selector metadata
  const exactText = rawText;

  // Quote: prefix + exact + suffix
  const prefixStart = Math.max(0, matchStart - 40);
  const prefix = fullText.slice(prefixStart, matchStart);
  const suffixEnd = Math.min(fullText.length, matchEnd + 40);
  const suffix = fullText.slice(matchEnd, suffixEnd);

  const metadata: HighlightSelectorMetadata = {
    selector_version: 1,
    text_range: { page: pageNumber, start: matchStart, end: matchEnd },
    quote: { exact: exactText, prefix, suffix },
    resolver: { method: 'selection' },
  };

  // Clear native selection — the overlay will handle the visual
  sel.removeAllRanges();

  setResult({
    selectionRect,
    displayRects,
    normalizedRects,
    selectedText: exactText,
    metadata,
  });
}

function getDomSelectionRects(
  range: Range,
  container: HTMLElement,
): Array<{ x: number; y: number; w: number; h: number }> {
  const containerRect = container.getBoundingClientRect();
  if (containerRect.width <= 0 || containerRect.height <= 0) return [];

  const pixelRects: Array<{
    left: number;
    top: number;
    right: number;
    bottom: number;
    width: number;
    height: number;
  }> = [];
  for (const r of range.getClientRects()) {
    const left = Math.max(r.left, containerRect.left);
    const top = Math.max(r.top, containerRect.top);
    const right = Math.min(r.right, containerRect.right);
    const bottom = Math.min(r.bottom, containerRect.bottom);
    const width = right - left;
    const height = bottom - top;

    if (width <= 0 || height <= 0) continue;
    pixelRects.push({ left, top, right, bottom, width, height });
  }

  return mergeSelectionRectsByLine(pixelRects).map((r) => ({
    x: (r.left - containerRect.left) / containerRect.width,
    y: (r.top - containerRect.top) / containerRect.height,
    w: r.width / containerRect.width,
    h: r.height / containerRect.height,
  }));
}

function mergeSelectionRectsByLine(
  rects: Array<{
    left: number;
    top: number;
    right: number;
    bottom: number;
    width: number;
    height: number;
  }>,
): Array<{
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}> {
  if (rects.length < 2) return rects;

  const heights = rects.map((r) => r.height).sort((a, b) => a - b);
  const medianHeight = heights[Math.floor((heights.length - 1) / 2)] || 1;
  const maxLineHeight = medianHeight * 2.5;
  const lineRects = rects.filter((r) => r.height <= maxLineHeight);
  if (lineRects.length === 0) return rects;

  const lines: Array<{
    top: number;
    bottom: number;
    intervals: Array<{ left: number; right: number }>;
  }> = [];

  for (const rect of [...lineRects].sort((a, b) => a.top - b.top || a.left - b.left)) {
    const rectCenter = (rect.top + rect.bottom) / 2;
    let line = lines.find((candidate) => {
      const overlap = Math.min(candidate.bottom, rect.bottom) - Math.max(candidate.top, rect.top);
      const candidateCenter = (candidate.top + candidate.bottom) / 2;
      return overlap >= Math.min(candidate.bottom - candidate.top, rect.height) * 0.6 ||
        Math.abs(candidateCenter - rectCenter) <= medianHeight * 0.4;
    });

    if (!line) {
      line = { top: rect.top, bottom: rect.bottom, intervals: [] };
      lines.push(line);
    }

    line.top = Math.min(line.top, rect.top);
    line.bottom = Math.max(line.bottom, rect.bottom);
    line.intervals.push({ left: rect.left, right: rect.right });
  }

  const merged: Array<{
    left: number;
    top: number;
    right: number;
    bottom: number;
    width: number;
    height: number;
  }> = [];
  const gapTolerance = Math.max(1, medianHeight * 0.25);

  for (const line of lines.sort((a, b) => a.top - b.top)) {
    const intervals = line.intervals.sort((a, b) => a.left - b.left);
    let current = { ...intervals[0] };

    for (const interval of intervals.slice(1)) {
      if (interval.left <= current.right + gapTolerance) {
        current.right = Math.max(current.right, interval.right);
      } else {
        merged.push(toPixelRect(current, line.top, line.bottom));
        current = { ...interval };
      }
    }
    merged.push(toPixelRect(current, line.top, line.bottom));
  }

  return merged;
}

function toPixelRect(
  interval: { left: number; right: number },
  top: number,
  bottom: number,
): {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
} {
  return {
    left: interval.left,
    top,
    right: interval.right,
    bottom,
    width: interval.right - interval.left,
    height: bottom - top,
  };
}

function resolveRangeOffsetsFromTextIndex(
  range: Range,
  container: HTMLElement,
  spanToItem: Map<Element, number>,
  index: PdfPageTextIndex,
): { start: number; end: number } | null {
  const start = resolveBoundaryOffsetFromTextIndex(
    range.startContainer,
    range.startOffset,
    container,
    spanToItem,
    index,
  );
  const end = resolveBoundaryOffsetFromTextIndex(
    range.endContainer,
    range.endOffset,
    container,
    spanToItem,
    index,
  );

  if (start === null || end === null || start >= end) return null;
  return { start, end };
}

function resolveBoundaryOffsetFromTextIndex(
  node: Node,
  offset: number,
  container: HTMLElement,
  spanToItem: Map<Element, number>,
  index: PdfPageTextIndex,
): number | null {
  const span = findMappedTextSpan(node, container, spanToItem);
  if (!span) return null;

  const itemIndex = spanToItem.get(span);
  const itemRange = itemIndex === undefined ? null : index.itemCharRanges[itemIndex];
  const item = itemIndex === undefined ? null : index.items[itemIndex];
  if (!itemRange || !item) return null;

  const localOffset = getTextOffsetWithinElement(span, node, offset);
  if (localOffset === null) return null;

  return itemRange.start + Math.min(localOffset, item.str.length);
}

function findMappedTextSpan(
  node: Node,
  container: HTMLElement,
  spanToItem: Map<Element, number>,
): Element | null {
  let el = node.nodeType === Node.ELEMENT_NODE
    ? (node as Element)
    : node.parentElement;

  while (el && container.contains(el)) {
    if (spanToItem.has(el)) return el;
    el = el.parentElement;
  }

  return null;
}

function getTextOffsetWithinElement(
  root: Element,
  boundaryNode: Node,
  boundaryOffset: number,
): number | null {
  if (boundaryNode.nodeType === Node.TEXT_NODE) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let total = 0;
    let textNode: Text | null;

    while ((textNode = walker.nextNode() as Text | null)) {
      if (textNode === boundaryNode) {
        return total + boundaryOffset;
      }
      total += textNode.textContent?.length ?? 0;
    }

    return null;
  }

  if (boundaryNode.nodeType !== Node.ELEMENT_NODE) return null;

  const el = boundaryNode as Element;
  if (!root.contains(el)) return null;

  let total = 0;
  const children = Array.from(el.childNodes).slice(0, boundaryOffset);
  for (const child of children) {
    total += child.textContent?.length ?? 0;
  }

  let parent: Node | null = el;
  while (parent && parent !== root) {
    const prevSiblings = previousSiblings(parent);
    for (const sibling of prevSiblings) {
      total += sibling.textContent?.length ?? 0;
    }
    parent = parent.parentNode;
  }

  return total;
}

function previousSiblings(node: Node): Node[] {
  const siblings: Node[] = [];
  let current = node.previousSibling;
  while (current) {
    siblings.unshift(current);
    current = current.previousSibling;
  }
  return siblings;
}

/** Check that the entire selection is contained within `container`. */
function isSelectionWithinElement(
  container: HTMLElement,
  sel: Selection,
): boolean {
  if (!sel.anchorNode || !sel.focusNode) return false;
  return (
    container.contains(sel.anchorNode) && container.contains(sel.focusNode)
  );
}
