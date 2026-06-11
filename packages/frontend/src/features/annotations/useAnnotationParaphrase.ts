import { useState, useCallback } from 'react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import {
  useParaphraseAnnotation,
  type ParaphraseLevel,
} from '@/api/chat';
import type { Annotation } from '@/api/annotations';
import { applyAiResultToAnnotation } from './annotationAiCache';

interface UseAnnotationParaphraseOptions {
  onSuccess?: (paraphrase: string, noteContent: string | null, annotationId: string) => void;
  onError?: (error: string) => void;
}

interface UseAnnotationParaphraseReturn {
  isParaphrasing: boolean;
  paraphrasingId: string | null;
  statusMessage: string;
  paraphrase: (annotation: Annotation, pdfId: string, level?: ParaphraseLevel) => void;
  clearParaphrase: () => void;
  explainUsesRemaining: number | null;
}

export function useAnnotationParaphrase(
  options: UseAnnotationParaphraseOptions = {},
): UseAnnotationParaphraseReturn {
  const { mutate: paraphraseAnnotation } = useParaphraseAnnotation();
  const queryClient = useQueryClient();

  const [paraphraseAnnotationId, setParaphraseAnnotationId] = useState<string | null>(null);
  const [paraphraseStatusMessage, setParaphraseStatusMessage] = useState<string>('');
  const [explainUsesRemaining, setExplainUsesRemaining] = useState<number | null>(null);

  const paraphrase = useCallback((
    annotation: Annotation,
    pdfId: string,
    level: ParaphraseLevel = 'same',
  ) => {
    if (!annotation.selected_text) {
      toast.error('Cannot paraphrase: annotation has no selected text');
      return;
    }

    setParaphraseAnnotationId(annotation.id);
    setParaphraseStatusMessage('Generating paraphrase...');

    paraphraseAnnotation(
      {
        pdf_id: pdfId,
        annotation_id: annotation.id,
        selected_text: annotation.selected_text,
        page_number: annotation.page_number,
        level,
      },
      {
        onSuccess: (result) => {
          setExplainUsesRemaining(result.explain_paraphrase_remaining);

          if (result.global_warning) {
            toast.info(result.global_warning);
          }

          if (result.provider_fallback) {
            toast.info('Free tier was busy — used backup model for this paraphrase.');
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

          options.onSuccess?.(result.paraphrase, result.note_content, annotation.id);

          setParaphraseStatusMessage('');
          setParaphraseAnnotationId(null);
        },
        onError: (err: Error) => {
          setParaphraseAnnotationId(null);
          setParaphraseStatusMessage('');
          const errorMsg = `Paraphrase failed: ${err.message}`;
          toast.error(errorMsg);
          options.onError?.(errorMsg);
        },
      },
    );
  }, [paraphraseAnnotation, queryClient, options]);

  const clearParaphrase = useCallback(() => {
    setParaphraseAnnotationId(null);
    setParaphraseStatusMessage('');
  }, []);

  return {
    isParaphrasing: paraphraseAnnotationId !== null,
    paraphrasingId: paraphraseAnnotationId,
    statusMessage: paraphraseStatusMessage,
    paraphrase,
    clearParaphrase,
    explainUsesRemaining,
  };
}
