import { create } from 'zustand';

interface ContextMenuState {
    x: number;
    y: number;
    annotationId: string;
}

interface AnnotationStore {
    isDrawingRect: boolean;
    selectedSetId: string | null;       // Which set is "active" for editing
    hiddenSetIds: Set<string>;          // Sets the user has hidden via eye toggle
    selectedAnnotationId: string | null;
    isSidebarOpen: boolean;
    sidebarGroupBy: 'page' | 'type';
    contextMenu: ContextMenuState | null;

    // Actions
    setIsDrawingRect: (drawing: boolean) => void;
    setSelectedSetId: (id: string | null) => void;
    setSelectedAnnotationId: (id: string | null) => void;
    toggleSetVisibility: (id: string) => void;
    isSetVisible: (id: string) => boolean;
    toggleSidebar: () => void;
    setSidebarOpen: (open: boolean) => void;
    setSidebarGroupBy: (groupBy: 'page' | 'type') => void;
    setContextMenu: (menu: ContextMenuState | null) => void;
}

export const useAnnotationStore = create<AnnotationStore>((set, get) => ({
    isDrawingRect: false,
    selectedSetId: null,
    hiddenSetIds: new Set<string>(),
    selectedAnnotationId: null,
    isSidebarOpen: true,
    sidebarGroupBy: 'page',
    contextMenu: null,

    setIsDrawingRect: (drawing) => set({
        isDrawingRect: drawing,
        ...(drawing ? { selectedAnnotationId: null } : {}),
    }),
    setSelectedSetId: (id) => set({ selectedSetId: id, selectedAnnotationId: null, contextMenu: null }),
    setSelectedAnnotationId: (id) => set({ selectedAnnotationId: id }),
    toggleSetVisibility: (id) => set((state) => {
        const next = new Set(state.hiddenSetIds);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        return { hiddenSetIds: next };
    }),
    isSetVisible: (id) => !get().hiddenSetIds.has(id),
    toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
    setSidebarOpen: (open) => set({ isSidebarOpen: open }),
    setSidebarGroupBy: (groupBy) => set({ sidebarGroupBy: groupBy }),
    setContextMenu: (menu) => set({ contextMenu: menu }),
}));
