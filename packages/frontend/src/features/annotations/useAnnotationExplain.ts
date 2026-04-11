import { useState, useCallback } from 'react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useExplainAnnotation } from '@/api/chat';

export interface Annotation {
    id: string;
    set_id: string;
    selected_text?: string | null;
    page_number: number;
}

export interface UseAnnotationExplainOptions {
    /** Called when explanation completes successfully */
    onSuccess?: (explanation: string, noteContent: string, annotationId: string) => void;
    /** Called when explanation fails */
    onError?: (error: string) => void;
}

export interface UseAnnotationExplainReturn {
    /** Whether an explanation is currently in progress */
    isExplaining: boolean;
    /** The ID of the annotation currently being explained */
    explainingId: string | null;
    /** Status message to display during explanation */
    statusMessage: string;
    /** Start an explanation for the given annotation */
    explain: (annotation: Annotation, pdfId: string) => void;
    /** Clear explanation state */
    clearExplain: () => void;
    /** Remaining explain uses (null before first call, -1 for unlimited/own-key users) */
    explainUsesRemaining: number | null;
}

/**
 * Hook for managing AI annotation explanation workflow.
 *
 * Handles:
 * - API call to explain endpoint
 * - Optimistic cache updates for immediate UI feedback
 * - Loading/error states
 * - Toast notifications for errors
 */
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
                    setExplainUsesRemaining(result.explain_uses_remaining);

                    if (result.provider_fallback) {
                        toast.info('Free tier was busy — used backup model for this explanation.');
                        queryClient.invalidateQueries({ queryKey: ['auto-highlight-quota'] });
                    }

                    // Optimistically update cache so NotePopover sees the new note_content immediately
                    queryClient.setQueryData(
                        ['annotations', annotation.set_id],
                        (old: Annotation[] | undefined) => {
                            if (!old) return old;
                            return old.map(a =>
                                a.id === annotation.id
                                    ? { ...a, note_content: result.note_content }
                                    : a
                            );
                        }
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
