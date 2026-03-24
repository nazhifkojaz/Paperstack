import { create } from 'zustand';

interface CitationStore {
    isPanelOpen: boolean;
    isEditing: boolean;
    togglePanel: () => void;
    setIsEditing: (isEditing: boolean) => void;
}

export const useCitationStore = create<CitationStore>((set) => ({
    isPanelOpen: false,
    isEditing: false,
    togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
    setIsEditing: (isEditing) => set({ isEditing }),
}));
