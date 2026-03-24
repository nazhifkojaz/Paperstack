/**
 * Shared utilities for computing precise text rects from pdf.js TextLayer.
 *
 * Used by both TextLayer (manual text selection) and useTextMatcher
 * (auto-highlight annotation resolution) to ensure consistent,
 * pixel-accurate highlight positioning.
 *
 * The key insight: pdf.js spans have scaleX transforms that inflate
 * DOM getClientRects(). Instead, we compute widths from the PDF's own
 * text item data (item.width × viewportScale), using canvas measureText
 * for proportional offsets within partially-selected spans.
 */

// ─── Types ──────────────────────────────────────────────────────────────────

/** PDF text item with position/width data from page.getTextContent() */
export interface PdfTextItem {
    str: string;
    width: number;
    height: number;
    transform: number[];
}

/** Optional PDF coordinate data for precise rect computation */
export interface PdfRectData {
    textItems: PdfTextItem[];
    spanToItemMap: Map<Element, number>;
    viewportScale: number;
}

/** Normalized 0-1 rect relative to the text layer container */
export type Rect = { x: number; y: number; w: number; h: number };

/** A DOM Text node with its character range in the concatenated fullText */
export type TextNode = { node: Text; start: number; end: number };

// ─── Canvas measurement ─────────────────────────────────────────────────────

let _measureCtx: CanvasRenderingContext2D | null = null;
function getMeasureCtx(): CanvasRenderingContext2D {
    if (!_measureCtx) _measureCtx = document.createElement('canvas').getContext('2d')!;
    return _measureCtx;
}

// ─── DOM helpers ────────────────────────────────────────────────────────────

/**
 * Walk the TextLayer DOM and build a concatenated fullText string with a
 * mapping from character positions back to DOM Text nodes.
 *
 * Inserts a space between text nodes from different parent spans,
 * since pdf.js renders each word/token as a separate <span> with no
 * whitespace between them in the DOM.
 */
export function collectTextNodes(container: HTMLDivElement): {
    textNodes: TextNode[];
    fullText: string;
} {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const textNodes: TextNode[] = [];
    let fullText = '';
    let prevParent: Node | null = null;
    let node: Text | null;

    while ((node = walker.nextNode() as Text | null)) {
        const parent = node.parentNode;

        // Insert a space when crossing a span boundary so words from
        // different spans don't fuse (e.g. "relevant" + "study" -> "relevant study").
        // Skip if either side already has whitespace to avoid double spaces.
        const content = node.textContent || '';
        if (
            prevParent !== null &&
            parent !== prevParent &&
            fullText.length > 0 &&
            !/\s$/.test(fullText) &&
            !/^\s/.test(content)
        ) {
            fullText += ' ';
        }

        const start = fullText.length;
        fullText += node.textContent || '';
        textNodes.push({ node, start, end: fullText.length });
        prevParent = parent;
    }

    return { textNodes, fullText };
}

// ─── Rect computation ───────────────────────────────────────────────────────

/**
 * Convert a character range in fullText to normalized 0-1 rects.
 *
 * When `pdfData` is provided, computes widths from the PDF text items'
 * coordinate data (item.width × viewportScale) instead of DOM getClientRects(),
 * which are inflated by pdf.js's scaleX transforms. Uses canvas measureText
 * for proportional offsets within partially-selected spans.
 *
 * Also trims trailing/leading whitespace from each node's range to avoid
 * rects extending into empty space (pdf.js uses white-space:pre).
 *
 * Falls back to DOM measurement when pdfData is not available.
 */
export function rangeToRects(
    textNodes: TextNode[],
    matchStart: number,
    matchEnd: number,
    containerRect: DOMRect,
    pdfData?: PdfRectData,
): Rect[] {
    if (matchStart >= matchEnd) return [];

    const rects: Rect[] = [];
    const hasPdf = pdfData && pdfData.textItems.length > 0 && pdfData.spanToItemMap.size > 0;
    const measureCtx = hasPdf ? getMeasureCtx() : null;

    for (const tn of textNodes) {
        // Skip nodes entirely outside the match range
        if (tn.end <= matchStart || tn.start >= matchEnd) continue;

        const text = tn.node.textContent || '';
        let startOffset = Math.max(0, matchStart - tn.start);
        let endOffset = Math.min(tn.node.length, matchEnd - tn.start);

        // Trim trailing whitespace to prevent rects from extending
        // into empty space (pdf.js spans use white-space:pre)
        const trimmedEnd = text.substring(0, endOffset).trimEnd().length;
        if (trimmedEnd > startOffset) endOffset = trimmedEnd;

        // Trim leading whitespace for non-start nodes
        if (startOffset === 0 && tn.start < matchStart) {
            // This node is fully inside the range — trim leading ws
            const trimmedStart = text.length - text.trimStart().length;
            if (trimmedStart < endOffset) startOffset = Math.max(startOffset, trimmedStart);
        }

        if (startOffset >= endOffset) continue;

        const parentSpan = tn.node.parentElement;
        const itemIdx = parentSpan && hasPdf ? pdfData!.spanToItemMap.get(parentSpan) : undefined;

        if (hasPdf && measureCtx && itemIdx !== undefined && parentSpan) {
            // --- Precise path: use PDF text item width ---
            const item = pdfData!.textItems[itemIdx];
            const itemViewportWidth = item.width * pdfData!.viewportScale;

            // Use span's bounding rect for position (left/top are correct
            // even with scaleX since transform-origin is 0% 0%)
            const spanRect = parentSpan.getBoundingClientRect();

            const computedStyle = window.getComputedStyle(parentSpan);
            measureCtx.font = `${computedStyle.fontSize} ${computedStyle.fontFamily}`;

            const fullMeasured = measureCtx.measureText(text).width;
            if (fullMeasured > 0) {
                const prefixText = text.substring(0, startOffset);
                const selectedText = text.substring(startOffset, endOffset);
                const prefixMeasured = measureCtx.measureText(prefixText).width;
                const selectedMeasured = measureCtx.measureText(selectedText).width;

                const prefixRatio = prefixMeasured / fullMeasured;
                const selectedRatio = selectedMeasured / fullMeasured;

                const rectLeft = spanRect.left + prefixRatio * itemViewportWidth;
                const rectWidth = selectedRatio * itemViewportWidth;
                const rectTop = spanRect.top;
                const rectHeight = spanRect.height;

                if (rectWidth > 0 && rectHeight > 0) {
                    rects.push({
                        x: (rectLeft - containerRect.left) / containerRect.width,
                        y: (rectTop - containerRect.top) / containerRect.height,
                        w: rectWidth / containerRect.width,
                        h: rectHeight / containerRect.height,
                    });
                }
            }
        } else {
            // --- Fallback: DOM measurement ---
            const range = document.createRange();
            range.setStart(tn.node, startOffset);
            range.setEnd(tn.node, endOffset);

            for (const r of range.getClientRects()) {
                if (r.width > 0 && r.height > 0) {
                    rects.push({
                        x: (r.left - containerRect.left) / containerRect.width,
                        y: (r.top - containerRect.top) / containerRect.height,
                        w: r.width / containerRect.width,
                        h: r.height / containerRect.height,
                    });
                }
            }
        }
    }

    return rects;
}

/**
 * Map a DOM Selection Range to character positions in the fullText built by
 * collectTextNodes, then compute precise rects.
 *
 * This is the entry point for TextLayer's manual text selection — it bridges
 * the DOM Range API to the character-position-based rangeToRects.
 */
export function selectionRangeToRects(
    range: Range,
    textNodes: TextNode[],
    containerRect: DOMRect,
    pdfData?: PdfRectData,
): Rect[] {
    // Map DOM Range start/end to character positions in fullText
    let startPos = 0;
    let endPos = 0;
    let foundStart = false;
    let foundEnd = false;

    for (const tn of textNodes) {
        if (!foundStart && tn.node === range.startContainer) {
            startPos = tn.start + range.startOffset;
            foundStart = true;
        }
        if (!foundEnd && tn.node === range.endContainer) {
            endPos = tn.start + range.endOffset;
            foundEnd = true;
        }
        if (foundStart && foundEnd) break;
    }

    // If start/end containers weren't found in textNodes (unlikely), bail
    if (!foundStart || !foundEnd) return [];

    return rangeToRects(textNodes, startPos, endPos, containerRect, pdfData);
}
