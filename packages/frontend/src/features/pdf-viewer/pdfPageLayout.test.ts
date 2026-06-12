import { describe, expect, it } from 'vitest';
import {
  buildPdfPageLayout,
  getPageAtViewportCenter,
  getPdfPageWindow,
  getScrollTopForPage,
  PDF_PAGE_INITIAL_WINDOW_COUNT,
} from './pdfPageLayout';

describe('pdfPageLayout', () => {
  it('builds cumulative page offsets without mounting every page', () => {
    const dimensions = new Map([
      [1, { baseWidth: 100, baseHeight: 200 }],
    ]);

    const layout = buildPdfPageLayout({
      totalPages: 100,
      pageDimensions: dimensions,
      zoom: 1,
      rotation: 0,
      pageGap: 10,
    });
    const windowedPages = getPdfPageWindow({
      pages: layout.pages,
      scrollTop: 0,
      viewportHeight: 500,
      overscanPx: 0,
    });

    expect(layout.pages).toHaveLength(100);
    expect(layout.totalHeight).toBe(21_000);
    expect(windowedPages.map((page) => page.pageNumber)).toEqual([1, 2, 3]);
  });

  it('estimates unknown pages from known dimensions until real dimensions arrive', () => {
    const dimensions = new Map([
      [1, { baseWidth: 100, baseHeight: 200 }],
      [3, { baseWidth: 300, baseHeight: 400 }],
    ]);

    const layout = buildPdfPageLayout({
      totalPages: 3,
      pageDimensions: dimensions,
      zoom: 1,
      rotation: 0,
      pageGap: 10,
    });

    expect(layout.pages[1]).toMatchObject({
      pageNumber: 2,
      top: 210,
      height: 200,
    });
    expect(layout.pages[2]).toMatchObject({
      pageNumber: 3,
      top: 420,
      height: 400,
    });
  });

  it('uses rotation and zoom when calculating page size', () => {
    const dimensions = new Map([
      [1, { baseWidth: 100, baseHeight: 200 }],
    ]);

    const layout = buildPdfPageLayout({
      totalPages: 1,
      pageDimensions: dimensions,
      zoom: 2,
      rotation: 90,
      pageGap: 10,
    });

    expect(layout.pages[0]).toMatchObject({
      height: 200,
      itemHeight: 210,
    });
  });

  it('returns a fallback initial window before the viewport is measured', () => {
    const layout = buildPdfPageLayout({
      totalPages: 10,
      pageDimensions: new Map(),
      zoom: 1,
      rotation: 0,
    });

    const windowedPages = getPdfPageWindow({
      pages: layout.pages,
      scrollTop: 0,
      viewportHeight: 0,
    });

    expect(windowedPages).toHaveLength(PDF_PAGE_INITIAL_WINDOW_COUNT);
  });

  it('finds the page at the viewport center from virtual offsets', () => {
    const dimensions = new Map([
      [1, { baseWidth: 100, baseHeight: 200 }],
    ]);
    const layout = buildPdfPageLayout({
      totalPages: 20,
      pageDimensions: dimensions,
      zoom: 1,
      rotation: 0,
      pageGap: 10,
    });

    expect(
      getPageAtViewportCenter({
        pages: layout.pages,
        scrollTop: layout.pages[9].top,
        viewportHeight: 200,
      }),
    ).toBe(10);
  });

  it('calculates scroll offsets for unmounted target pages', () => {
    const dimensions = new Map([
      [1, { baseWidth: 100, baseHeight: 200 }],
    ]);
    const layout = buildPdfPageLayout({
      totalPages: 100,
      pageDimensions: dimensions,
      zoom: 1,
      rotation: 0,
      pageGap: 10,
    });
    const targetPage = layout.pages[79];

    expect(getScrollTopForPage(targetPage, 500, 0.5)).toBe(
      targetPage.top + 100 - 250,
    );
  });
});
