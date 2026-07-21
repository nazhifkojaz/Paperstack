import { create } from 'zustand';

interface SummaryStore {
    isSummaryPanelOpen: boolean;
    toggleSummaryPanel: () => void;
    setSummaryPanelOpen: (open: boolean) => void;
}

export const useSummaryStore = create<SummaryStore>((set) => ({
    isSummaryPanelOpen: false,
    toggleSummaryPanel: () => set((state) => ({ isSummaryPanelOpen: !state.isSummaryPanelOpen })),
    setSummaryPanelOpen: (open) => set({ isSummaryPanelOpen: open }),
}));
