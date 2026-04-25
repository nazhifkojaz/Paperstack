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

/** A DOM Text node with its character range in the concatenated fullText */
export type TextNode = { node: Text; start: number; end: number };

/** Ref handle interface for TextLayer component */
export interface TextLayerHandle {
    getContainer: () => HTMLDivElement | null;
    renderReady: () => Promise<void>;
    getTextItems: () => PdfTextItem[];
    getSpanToItemMap: () => Map<Element, number>;
    getViewportScale: () => number;
    getRenderId: () => number;
}
