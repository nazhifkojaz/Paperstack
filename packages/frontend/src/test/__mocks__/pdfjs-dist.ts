/**
 * Mock for pdfjs-dist library.
 *
 * This mock provides simulated PDF.js functionality for tests,
 * avoiding the need to load the actual PDF.js library.
 */

import { vi } from 'vitest'

// =============================================================================
// Mock PDF Document Proxy
// =============================================================================

class MockPDFPageProxy {
  constructor(_pageNum: number) {}

  async getViewport(params: { scale: number; rotation?: number }) {
    return {
      view: [0, 0, 612, 792],
      rotation: params.rotation || 0,
      scale: params.scale,
      transform: [params.scale, 0, 0, params.scale, 0, 0],
      width: 612 * params.scale,
      height: 792 * params.scale,
    }
  }

  async render(_params: { canvasContext: any; viewport: any }) {
    // Simulate async render operation
    return {
      promise: Promise.resolve(undefined),
    }
  }

  async getTextContent() {
    return {
      items: [
        { str: 'Sample text', dir: 'ltr', width: 50, height: 12, transform: [1, 0, 0, 1, 100, 100] },
      ],
    }
  }

  streamTextContent() {
    return new ReadableStream({
      start(controller) {
        controller.enqueue({
          items: [
            { str: 'Sample text', dir: 'ltr', width: 50, height: 12, transform: [1, 0, 0, 1, 100, 100] },
          ],
        })
        controller.close()
      },
    })
  }
}

class MockPDFDocumentProxy {
  constructor(
    public numPages: number = 10,
    public fingerprint: string = 'mock-fingerprint'
  ) {}

  async getPage(pageNumber: number) {
    if (pageNumber < 1 || pageNumber > this.numPages) {
      throw new Error('Page index out of bounds')
    }
    return new MockPDFPageProxy(pageNumber)
  }

  async getOutline() {
    return null
  }

  async getMetadata() {
    return {
      info: {
        Title: 'Mock PDF',
        Author: 'Test Author',
        Subject: 'Test Subject',
      },
      metadata: null,
    }
  }

  destroy() {
    // Cleanup mock
  }
}

// =============================================================================
// Mock getDocument Function
// =============================================================================

const getDocument = vi.fn((src: string | any) => {
  // Handle different src types
  let loadingTask: any = {
    promise: Promise.resolve(new MockPDFDocumentProxy()),
    destroy: vi.fn(),
    onPassword: vi.fn(),
    onProgress: vi.fn(),
  }

  // Handle custom document properties
  if (typeof src === 'object' && src?.data) {
    // Buffer or array source
    loadingTask.promise = Promise.resolve(new MockPDFDocumentProxy(src.numPages || 10))
  }

  return loadingTask
})

// =============================================================================
// Mock TextLayer Class (v5+)
// =============================================================================

class MockTextLayer {
  constructor(_params: any) {}
  render = vi.fn(() => Promise.resolve())
  cancel = vi.fn()
}

const TextLayer = MockTextLayer

// =============================================================================
// Mock Global Worker Options
// =============================================================================

const GlobalWorkerOptions = {
  workerSrc: '',
  workerPort: null as any,
}

// =============================================================================
// Export Mock
// =============================================================================

export default {
  getDocument,
  TextLayer,
  GlobalWorkerOptions,
  PDFDocumentProxy: MockPDFDocumentProxy,
  PDFPageProxy: MockPDFPageProxy,
}

// Also export named exports
export const {
  getDocument: getDocumentExport,
  TextLayer: TextLayerExport,
  GlobalWorkerOptions: GlobalWorkerOptionsExport,
} = {
  getDocument,
  TextLayer,
  GlobalWorkerOptions,
}
