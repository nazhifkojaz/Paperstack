import { useState, useCallback } from 'react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useExplainAnnotation } from '@/api/chat';
import type { Annotation } from '@/api/annotations';
import { applyAiResultToAnnotation } from './annotationAiCache';

interface UseAnnotationExplainOptions {
    onSuccess?: (explanation: string, noteContent: string | null, annotationId: string) => void;
    onError?: (error: string) => void;
}

interface UseAnnotationExplainReturn {
    isExplaining: boolean;
    explainingId: string | null;
    statusMessage: string;
    explain: (annotation: Annotation, pdfId: string) => void;
    clearExplain: () => void;
    explainUsesRemaining: number | null;
}

export function useAnnotationExplain(options: UseAnnotationExplainOptions = {}): UseAnnotationExplainReturn {
    const { mutate: explainAnnotation } = useExplainAnnotation();
    const queryClient = useQueryClient();

    const [explainAnnotationId, setExplainAnnotationId] = useState<string | null>(null);
    const [explainStatusMessage, setExplainStatusMessage] = useState<string>('');
    const [explainUsesRemaining, setExplainUsesRemaining] = useState<number | null>(null);

    const explain = useCallback((annotation: Annotation, pdfId: string) => {
        if (!annotation.selected_text) {
            toast.error('Cannot explain: annotation has no selected text');
            return;
        }

        setExplainAnnotationId(annotation.id);
        setExplainStatusMessage('Generating explanation...');

        explainAnnotation(
            {
                pdf_id: pdfId,
                annotation_id: annotation.id,
                selected_text: annotation.selected_text,
                page_number: annotation.page_number,
            },
            {
                onSuccess: (result) => {
                    setExplainUsesRemaining(result.explain_paraphrase_remaining);

                    if (result.global_warning) {
                        toast.info(result.global_warning);
                    }

                    if (result.provider_fallback) {
                        toast.info('Free tier was busy — used backup model for this explanation.');
                        queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
                    }

                    const applyResult = applyAiResultToAnnotation(
                        annotation.id,
                        result.note_content,
                        result.metadata,
                    );
                    queryClient.setQueriesData<Annotation[]>(
                        { queryKey: ['annotations'] },
                        applyResult,
                    );

                    // Call onSuccess before resetting state (so annotation ID is available)
                    options.onSuccess?.(result.explanation, result.note_content, annotation.id);

                    // Reset state after everything else
                    setExplainStatusMessage('');
                    setExplainAnnotationId(null);
                },
                onError: (err: Error) => {
                    setExplainAnnotationId(null);
                    setExplainStatusMessage('');
                    const errorMsg = `Explanation failed: ${err.message}`;
                    toast.error(errorMsg);
                    options.onError?.(errorMsg);
                },
            }
        );
    }, [explainAnnotation, queryClient, options]);

    const clearExplain = useCallback(() => {
        setExplainAnnotationId(null);
        setExplainStatusMessage('');
    }, []);

    return {
        isExplaining: explainAnnotationId !== null,
        explainingId: explainAnnotationId,
        statusMessage: explainStatusMessage,
        explain,
        clearExplain,
        explainUsesRemaining,
    };
}
