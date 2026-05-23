// ---------------------------------------------------------------------------
// PdfChatHighlightLayer.tsx — Temporary chat‑snippet highlights
// ---------------------------------------------------------------------------
// Reads `chatHighlightStore.pendingHighlight` and when the snippet matches
// the current page, resolves it via the text index and renders temporary
// yellow highlight rects.  Clears after 5 seconds.
// ---------------------------------------------------------------------------

import { useEffect, useState } from 'react';
import { useChatHighlightStore } from '@/stores/chatHighlightStore';
import type { PdfTextLayerHandle } from './PdfTextLayer';
import { searchTextIndex } from './pdfSearch';
import { textRangeToNormalizedRects } from './pdfGeometry';
import { useNewPdfViewerStore } from './pdfViewerStore';
import type { PdfViewportInfo } from './pdfViewerTypes';

// ---------------------------------------------------------------------------
// Interface
// ---------------------------------------------------------------------------

interface PdfChatHighlightLayerProps {
  pageNumber: number;
  textLayerRef?: React.RefObject<PdfTextLayerHandle | null>;
}

const HIGHLIGHT_DURATION_MS = 5000;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const PdfChatHighlightLayer = ({
  pageNumber,
  textLayerRef,
}: PdfChatHighlightLayerProps) => {
  const [rects, setRects] = useState<
    Array<{ x: number; y: number; w: number; h: number }>
  >([]);

  const pendingHighlight = useChatHighlightStore(
    (s) => s.pendingHighlight,
  );
  const setPendingHighlight = useChatHighlightStore(
    (s) => s.setPendingHighlight,
  );

  const dimensions = useNewPdfViewerStore((s) =>
    s.pageDimensions.get(pageNumber),
  );
  const zoom = useNewPdfViewerStore((s) => s.zoom);

  useEffect(() => {
    if (
      !pendingHighlight ||
      !textLayerRef?.current ||
      pendingHighlight.pageNumber !== pageNumber
    ) {
      queueMicrotask(() => setRects([]));
      return;
    }

    if (!dimensions) return;

    const handle = textLayerRef.current;

    handle.renderReady().then(() => {
      const index = handle.getTextIndex();
      if (!index) {
        setRects([]);
        return;
      }

      const snippet = pendingHighlight.snippet.trim();
      if (!snippet) {
        setRects([]);
        return;
      }

      const match = searchTextIndex(index, snippet);
      if (!match) {
        setRects([]);
        return;
      }

      const viewport: PdfViewportInfo = {
        width: dimensions.baseWidth,
        height: dimensions.baseHeight,
        rotation: 0,
        scale: zoom,
      };

      const computedRects = textRangeToNormalizedRects(
        index,
        match.start,
        match.end,
        viewport,
      );

      const validRects = computedRects.filter(
        (r) => r.w > 0.001 && r.h > 0.001,
      );
      setRects(validRects);
    });

    // Auto‑clear after duration
    const timeout = setTimeout(() => {
      setRects([]);
      setPendingHighlight(null);
    }, HIGHLIGHT_DURATION_MS);

    return () => clearTimeout(timeout);
  }, [
    pendingHighlight,
    pageNumber,
    textLayerRef,
    dimensions,
    zoom,
    setPendingHighlight,
  ]);

  if (rects.length === 0) return null;

  // Compute viewport pixel dimensions for SVG
  const vpW = dimensions ? dimensions.baseWidth * zoom : 612;
  const vpH = dimensions ? dimensions.baseHeight * zoom : 792;

  return (
    <svg
      className="absolute inset-0 pointer-events-none z-25"
      style={{
        width: `${vpW}px`,
        height: `${vpH}px`,
      }}
      aria-hidden
    >
      {rects.map((r, i) => (
        <rect
          key={`chat-${i}`}
          x={r.x * vpW}
          y={r.y * vpH}
          width={r.w * vpW}
          height={r.h * vpH}
          rx={2}
          ry={2}
          fill="rgba(255, 200, 50, 0.45)"
          stroke="rgba(255, 180, 30, 0.8)"
          strokeWidth={1}
        />
      ))}
    </svg>
  );
};
