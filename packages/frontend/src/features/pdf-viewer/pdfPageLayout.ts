import type { PdfViewerRotation } from './pdfViewerTypes';

export interface PageDimensions {
  baseWidth: number;
  baseHeight: number;
}

interface PageViewportSize {
  width: number;
  height: number;
}

export interface PdfPageLayout {
  pageNumber: number;
  top: number;
  height: number;
  itemHeight: number;
  dimensions: PageDimensions;
}

export const DEFAULT_PAGE_DIMENSIONS: PageDimensions = {
  baseWidth: 612,
  baseHeight: 792,
};

export const PDF_PAGE_GAP_PX = 24;
export const PDF_PAGE_WINDOW_OVERSCAN_PX = 1200;
export const PDF_PAGE_INITIAL_WINDOW_COUNT = 4;

export function getPageDimensionsFromViewport(
  viewport: PageViewportSize,
): PageDimensions {
  return {
    baseWidth: viewport.width,
    baseHeight: viewport.height,
  };
}

export function getEstimatedPageDimensions(
  pageDimensions: Map<number, PageDimensions>,
  preferredPage = 1,
): PageDimensions {
  return (
    pageDimensions.get(preferredPage) ??
    pageDimensions.get(1) ??
    pageDimensions.values().next().value ??
    DEFAULT_PAGE_DIMENSIONS
  );
}

export function getBasePageWidthForRotation(
  dimensions: PageDimensions,
  rotation: PdfViewerRotation,
): number {
  return rotation === 90 || rotation === 270
    ? dimensions.baseHeight
    : dimensions.baseWidth;
}

export function getBasePageHeightForRotation(
  dimensions: PageDimensions,
  rotation: PdfViewerRotation,
): number {
  return rotation === 90 || rotation === 270
    ? dimensions.baseWidth
    : dimensions.baseHeight;
}

export function getScaledPageSize(
  dimensions: PageDimensions,
  zoom: number,
  rotation: PdfViewerRotation,
): { width: number; height: number } {
  return {
    width: getBasePageWidthForRotation(dimensions, rotation) * zoom,
    height: getBasePageHeightForRotation(dimensions, rotation) * zoom,
  };
}

export function buildPdfPageLayout({
  totalPages,
  pageDimensions,
  zoom,
  rotation,
  pageGap = PDF_PAGE_GAP_PX,
}: {
  totalPages: number;
  pageDimensions: Map<number, PageDimensions>;
  zoom: number;
  rotation: PdfViewerRotation;
  pageGap?: number;
}): { pages: PdfPageLayout[]; totalHeight: number } {
  const pages: PdfPageLayout[] = [];
  let top = 0;
  const fallbackDimensions = getEstimatedPageDimensions(pageDimensions);

  for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
    const dimensions = pageDimensions.get(pageNumber) ?? fallbackDimensions;
    const { height } = getScaledPageSize(dimensions, zoom, rotation);
    const itemHeight = height + pageGap;

    pages.push({
      pageNumber,
      top,
      height,
      itemHeight,
      dimensions,
    });
    top += itemHeight;
  }

  return { pages, totalHeight: top };
}

export function getPdfPageWindow({
  pages,
  scrollTop,
  viewportHeight,
  overscanPx = PDF_PAGE_WINDOW_OVERSCAN_PX,
}: {
  pages: PdfPageLayout[];
  scrollTop: number;
  viewportHeight: number;
  overscanPx?: number;
}): PdfPageLayout[] {
  if (pages.length === 0) return [];

  if (viewportHeight <= 0) {
    return pages.slice(0, PDF_PAGE_INITIAL_WINDOW_COUNT);
  }

  const start = Math.max(0, scrollTop - overscanPx);
  const end = scrollTop + viewportHeight + overscanPx;
  const startIndex = pages.findIndex((page) => page.top + page.itemHeight >= start);

  if (startIndex === -1) {
    return pages.slice(-PDF_PAGE_INITIAL_WINDOW_COUNT);
  }

  let endIndex = startIndex;
  while (endIndex < pages.length && pages[endIndex].top <= end) {
    endIndex += 1;
  }

  return pages.slice(startIndex, Math.max(endIndex, startIndex + 1));
}

export function getScrollTopForPage(
  page: PdfPageLayout,
  viewportHeight: number,
  ratioY = 0,
): number {
  return Math.max(0, page.top + page.height * ratioY - viewportHeight / 2);
}

export function hasSameDimensions(
  left: PageDimensions | undefined,
  right: PageDimensions,
): boolean {
  return (
    left?.baseWidth === right.baseWidth &&
    left?.baseHeight === right.baseHeight
  );
}
