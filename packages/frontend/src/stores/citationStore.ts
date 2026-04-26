import { create } from 'zustand';

interface CitationStore {
    isCitationPanelOpen: boolean;
    isEditing: boolean;
    toggleCitationPanel: () => void;
    setCitationPanelOpen: (open: boolean) => void;
    setIsEditing: (isEditing: boolean) => void;
}

export const useCitationStore = create<CitationStore>((set) => ({
    isCitationPanelOpen: false,
    isEditing: false,
    toggleCitationPanel: () => set((state) => ({ isCitationPanelOpen: !state.isCitationPanelOpen })),
    setCitationPanelOpen: (open) => set({ isCitationPanelOpen: open }),
    setIsEditing: (isEditing) => set({ isEditing }),
}));
