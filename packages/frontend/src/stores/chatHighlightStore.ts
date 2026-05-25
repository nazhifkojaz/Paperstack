import { create } from 'zustand';

interface PendingHighlight {
    pdfId: string;
    pageNumber: number;
    snippet: string;
}

interface ChatHighlightStore {
    pendingHighlight: PendingHighlight | null;
    setPendingHighlight: (highlight: PendingHighlight | null) => void;
}

export const useChatHighlightStore = create<ChatHighlightStore>((set) => ({
    pendingHighlight: null,
    setPendingHighlight: (highlight) => set({ pendingHighlight: highlight }),
}));
