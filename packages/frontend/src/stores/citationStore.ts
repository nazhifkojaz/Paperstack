import { create } from 'zustand';

interface CitationStore {
    isCitationPanelOpen: boolean;
    isEditing: boolean;
    toggleCitationPanel: () => void;
    setIsEditing: (isEditing: boolean) => void;
}

export const useCitationStore = create<CitationStore>((set) => ({
    isCitationPanelOpen: false,
    isEditing: false,
    toggleCitationPanel: () => set((state) => ({ isCitationPanelOpen: !state.isCitationPanelOpen })),
    setIsEditing: (isEditing) => set({ isEditing }),
}));
