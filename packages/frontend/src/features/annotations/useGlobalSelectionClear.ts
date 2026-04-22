import { useEffect } from 'react';
import { useAnnotationStore } from '@/stores/annotationStore';

export function useGlobalSelectionClear() {
    const clear = useAnnotationStore(s => s.setSelectedAnnotationId);
    useEffect(() => {
        const handler = () => clear(null);
        document.addEventListener('scroll', handler, true);
        document.addEventListener('click', handler);
        return () => {
            document.removeEventListener('scroll', handler, true);
            document.removeEventListener('click', handler);
        };
    }, [clear]);
}
