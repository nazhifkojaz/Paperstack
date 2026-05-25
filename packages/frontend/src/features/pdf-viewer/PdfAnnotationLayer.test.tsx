import { fireEvent, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Annotation } from '@/api/annotations'
import type { Rect } from '@/types/annotation'
import { PdfAnnotationLayer } from './PdfAnnotationLayer'
import { useAnnotationCreation } from './useAnnotationCreation'
import { useAnnotationLayerState } from './useAnnotationLayerState'

vi.mock('./useAnnotationCreation', () => ({
  useAnnotationCreation: vi.fn(),
}))

vi.mock('./useAnnotationLayerState', () => ({
  useAnnotationLayerState: vi.fn(),
}))

vi.mock('./AnnotationLayerToolbar', () => ({
  AnnotationLayerToolbar: ({ selectedAnnotationId }: { selectedAnnotationId: string | null }) => (
    <div data-testid="annotation-layer-toolbar" data-selected-id={selectedAnnotationId ?? ''} />
  ),
}))

const mockUseAnnotationCreation = vi.mocked(useAnnotationCreation)
const mockUseAnnotationLayerState = vi.mocked(useAnnotationLayerState)

const defaultRect: Rect = { x: 0.1, y: 0.2, w: 0.3, h: 0.4 }

function makeAnnotation(overrides: Partial<Annotation> = {}): Annotation {
  return {
    id: 'annotation-1',
    set_id: 'set-1',
    page_number: 1,
    type: 'rect',
    rects: [defaultRect],
    selected_text: null,
    note_content: null,
    color: '#ff0000',
    metadata: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeCreation(overrides = {}) {
  return {
    previewRect: null,
    handleMouseDown: vi.fn(),
    handleMouseMove: vi.fn(),
    handleMouseUp: vi.fn(),
    handleMouseLeave: vi.fn(),
    ...overrides,
  }
}

function makeLayerState(overrides: Record<string, unknown> = {}) {
  const annotation = makeAnnotation()

  return {
    annotationExplain: {
      clearExplain: vi.fn(),
      explainUsesRemaining: null,
      explainingId: null,
      isExplaining: false,
      statusMessage: '',
    },
    closeContextMenu: vi.fn(),
    containerDims: null,
    containerElement: null,
    containerRef: { current: null },
    contextMenu: null,
    drag: {
      isDragging: false,
      previewRect: null,
      previewRects: null,
      startMove: vi.fn(),
      startResize: vi.fn(),
    },
    editingNoteId: null,
    handleExplainThis: vi.fn(),
    isDrawingRect: false,
    openContextMenu: vi.fn(),
    pageAnnotations: [annotation],
    resolveRects: vi.fn((ann: Annotation) => ann.rects),
    rotation: 0,
    selectedAnnotationId: null,
    selectedSetId: 'set-1',
    setEditingNoteId: vi.fn(),
    setIsDrawingRect: vi.fn(),
    setSelectedAnnotationId: vi.fn(),
    visibleSetIds: ['set-1'],
    ...overrides,
  }
}

describe('PdfAnnotationLayer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAnnotationCreation.mockReturnValue(makeCreation() as any)
    mockUseAnnotationLayerState.mockReturnValue(makeLayerState() as any)
  })

  it('does not render when no annotation sets are visible or selected', () => {
    mockUseAnnotationLayerState.mockReturnValue(makeLayerState({
      selectedSetId: null,
      visibleSetIds: [],
    }) as any)

    const { container } = render(<PdfAnnotationLayer pageNumber={1} pdfId="pdf-1" />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders annotation rectangles and wires selection and context menu events', () => {
    const annotation = makeAnnotation()
    const openContextMenu = vi.fn()
    const setSelectedAnnotationId = vi.fn()

    mockUseAnnotationLayerState.mockReturnValue(makeLayerState({
      openContextMenu,
      pageAnnotations: [annotation],
      setSelectedAnnotationId,
    }) as any)

    const { container } = render(<PdfAnnotationLayer pageNumber={1} pdfId="pdf-1" />)

    const layer = container.firstElementChild as HTMLElement
    const rect = container.querySelector('svg g rect') as SVGRectElement

    expect(layer).toHaveClass('pointer-events-none')
    expect(rect).toHaveAttribute('x', '10%')
    expect(rect).toHaveAttribute('y', '20%')
    expect(rect).toHaveAttribute('width', '30%')
    expect(rect).toHaveAttribute('height', '40%')

    fireEvent.click(rect)
    expect(setSelectedAnnotationId).toHaveBeenCalledWith('annotation-1')

    fireEvent.contextMenu(rect, { clientX: 120, clientY: 240 })
    expect(openContextMenu).toHaveBeenCalledWith({
      x: 120,
      y: 240,
      annotationId: 'annotation-1',
    })

    fireEvent.click(layer)
    expect(setSelectedAnnotationId).toHaveBeenCalledWith(null)
  })

  it('enables drawing mode and ends drawing through the creation hook callback', () => {
    const creation = makeCreation({
      previewRect: { x: 0.2, y: 0.3, w: 0.1, h: 0.2 },
    })
    const setIsDrawingRect = vi.fn()

    mockUseAnnotationCreation.mockReturnValue(creation as any)
    mockUseAnnotationLayerState.mockReturnValue(makeLayerState({
      isDrawingRect: true,
      pageAnnotations: [],
      rotation: 90,
      setIsDrawingRect,
    }) as any)

    const { container } = render(<PdfAnnotationLayer pageNumber={2} pdfId="pdf-1" />)
    const layer = container.firstElementChild as HTMLElement

    expect(layer).toHaveClass('pointer-events-auto')
    expect(layer).toHaveClass('cursor-crosshair')

    fireEvent.mouseDown(layer)
    fireEvent.mouseMove(layer)
    fireEvent.mouseUp(layer)

    expect(creation.handleMouseDown).toHaveBeenCalled()
    expect(creation.handleMouseMove).toHaveBeenCalled()
    expect(creation.handleMouseUp).toHaveBeenCalled()
    expect(container.querySelector('svg rect')).toHaveAttribute('x', '20%')

    const creationOptions = mockUseAnnotationCreation.mock.calls[0][0]
    expect(creationOptions).toEqual(expect.objectContaining({
      isDrawingRect: true,
      pageNumber: 2,
      rotation: 90,
      selectedSetId: 'set-1',
    }))

    creationOptions.onDrawingEnd()
    expect(setIsDrawingRect).toHaveBeenCalledWith(false)
  })

  it('starts moving and resizing the selected rectangle without bubbling events', () => {
    const annotation = makeAnnotation()
    const startMove = vi.fn()
    const startResize = vi.fn()

    mockUseAnnotationLayerState.mockReturnValue(makeLayerState({
      drag: {
        isDragging: false,
        previewRect: null,
        previewRects: null,
        startMove,
        startResize,
      },
      pageAnnotations: [annotation],
      selectedAnnotationId: 'annotation-1',
    }) as any)

    const { container } = render(<PdfAnnotationLayer pageNumber={1} pdfId="pdf-1" />)
    const annotationGroup = container.querySelector('svg g') as SVGGElement
    const resizeHandle = container.querySelector('rect[fill="white"]') as SVGRectElement

    fireEvent.mouseDown(annotationGroup)
    expect(startMove).toHaveBeenCalledWith(expect.any(Object), [defaultRect])

    fireEvent.mouseDown(resizeHandle)
    expect(startResize).toHaveBeenCalledWith('nw', expect.any(Object), defaultRect)
  })
})
