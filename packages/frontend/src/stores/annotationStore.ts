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
    isAnnotationSidebarOpen: boolean;
    isAnnotationSidebarCollapsed: boolean;
    sidebarGroupBy: 'page' | 'type';
    contextMenu: ContextMenuState | null;

    // Actions
    setIsDrawingRect: (drawing: boolean) => void;
    setSelectedSetId: (id: string | null) => void;
    setSelectedAnnotationId: (id: string | null) => void;
    toggleSetVisibility: (id: string) => void;
    isSetVisible: (id: string) => boolean;
    toggleAnnotationSidebar: () => void;
    setAnnotationSidebarOpen: (open: boolean) => void;
    setAnnotationSidebarCollapsed: (collapsed: boolean) => void;
    setSidebarGroupBy: (groupBy: 'page' | 'type') => void;
    setContextMenu: (menu: ContextMenuState | null) => void;
}

export const useAnnotationStore = create<AnnotationStore>((set, get) => ({
    isDrawingRect: false,
    selectedSetId: null,
    hiddenSetIds: new Set<string>(),
    selectedAnnotationId: null,
    isAnnotationSidebarOpen: true,
    isAnnotationSidebarCollapsed: false,
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
    toggleAnnotationSidebar: () => set((state) => {
        const nextCollapsed = !state.isAnnotationSidebarCollapsed;
        return {
            isAnnotationSidebarCollapsed: nextCollapsed,
            // When expanding, ensure sidebar is marked as open
            ...(nextCollapsed === false ? { isAnnotationSidebarOpen: true } : {}),
        };
    }),
    setAnnotationSidebarOpen: (open) => set({
        isAnnotationSidebarOpen: open,
        // If closing entirely, also collapse
        ...(open === false ? { isAnnotationSidebarCollapsed: true } : {}),
    }),
    setAnnotationSidebarCollapsed: (collapsed) => set({
        isAnnotationSidebarCollapsed: collapsed,
        ...(collapsed === false ? { isAnnotationSidebarOpen: true } : {}),
    }),
    setSidebarGroupBy: (groupBy) => set({ sidebarGroupBy: groupBy }),
    setContextMenu: (menu) => set({ contextMenu: menu }),
}));
