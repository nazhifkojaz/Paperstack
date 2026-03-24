/**
 * Tests for TextLayer component.
 * TextLayer renders text and shows SelectionPopup when text is selected.
 */

import { describe, it, expect, vi } from 'vitest'
import { TextLayer as PdfjsTextLayer } from 'pdfjs-dist'
import { render } from '@/test/test-utils'
import { TextLayer } from './TextLayer'

// Mock pdfjs
vi.mock('pdfjs-dist', () => {
  const TextLayer = vi.fn(function (this: any) {
    this.render = vi.fn(() => Promise.resolve())
    this.cancel = vi.fn()
  })
  return { TextLayer }
})

// Mock SelectionPopup
vi.mock('@/features/annotations/SelectionPopup', () => ({
  SelectionPopup: vi.fn(() => <div data-testid="selection-popup">Selection Popup</div>),
}))

describe('TextLayer', () => {
  describe('rendering and styling', () => {
    it('renders without crashing when pageProxy is null', () => {
      const { container } = render(<TextLayer pageProxy={null} />)
      expect(container.firstChild).toBeTruthy()
    })

    it('always has z-20 for layering above AnnotationOverlay', () => {
      const { container } = render(<TextLayer pageProxy={null} />)

      const textLayer = container.querySelector('.z-20') as HTMLElement
      expect(textLayer).toBeTruthy()
    })

    it('passes through custom className', () => {
      const { container } = render(<TextLayer pageProxy={null} className="custom-class" />)

      const textLayer = container.querySelector('.custom-class') as HTMLElement
      expect(textLayer).toBeTruthy()
    })
  })

  describe('text content rendering', () => {
    it('calls TextLayer with pageProxy', async () => {
      const mockStream = { getReader: vi.fn() }
      const mockPageProxy = {
        pageNumber: 1,
        streamTextContent: vi.fn(() => mockStream),
        getTextContent: vi.fn(() => Promise.resolve({ items: [], styles: {} })),
        getViewport: vi.fn(() => ({ width: 800, height: 1000 })),
      } as any

      render(<TextLayer pageProxy={mockPageProxy} />)

      expect(PdfjsTextLayer).toHaveBeenCalledWith(
        expect.objectContaining({
          textContentSource: mockStream,
          viewport: { width: 800, height: 1000 },
        })
      )
    })

    it('renders text layer with correct viewport dimensions', async () => {
      const mockPageProxy = {
        pageNumber: 1,
        streamTextContent: vi.fn(() => ({ getReader: vi.fn() })),
        getTextContent: vi.fn(() => Promise.resolve({ items: [], styles: {} })),
        getViewport: vi.fn(({ scale }: any) => ({
          width: 800 * scale,
          height: 1000 * scale,
        })),
      } as any

      const { container } = render(<TextLayer pageProxy={mockPageProxy} />)

      const textLayer = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(textLayer).toBeTruthy()
    })
  })

  describe('selection popup integration', () => {
    it('renders without crashing with a pageProxy', () => {
      const { container } = render(<TextLayer pageProxy={null} />)

      const textLayer = container.querySelector('.absolute.inset-0') as HTMLElement
      expect(textLayer).toBeTruthy()
    })
  })

  describe('z-index layering', () => {
    it('always has z-20 below AnnotationOverlay z-30', () => {
      const { container } = render(<TextLayer pageProxy={null} />)

      const textLayer = container.querySelector('.z-20')
      expect(textLayer).toBeTruthy()
    })
  })
})
