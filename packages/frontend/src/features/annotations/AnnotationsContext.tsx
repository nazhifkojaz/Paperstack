import { createContext, useContext } from 'react';
import type { Annotation, AnnotationSet } from '@/api/annotations';

export interface AnnotationsContextValue {
    allSets: AnnotationSet[];
    visibleSetIds: string[];
    annotationsByPage: Map<number, Annotation[]>;
}

export const AnnotationsContext = createContext<AnnotationsContextValue | null>(null);

export function useAnnotationsContext(): AnnotationsContextValue {
    const ctx = useContext(AnnotationsContext);
    if (!ctx) throw new Error('useAnnotationsContext must be used within AnnotationsContext.Provider');
    return ctx;
}
