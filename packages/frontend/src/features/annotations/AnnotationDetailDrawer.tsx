import { useEffect, useMemo, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { FileText, Loader2, Pencil, Save } from 'lucide-react';
import type { Annotation } from '@/api/annotations';
import type { ParaphraseLevel } from '@/api/chat';
import { useUpdateAnnotation } from '@/api/annotations';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { AnnotationAiActionControls } from './AnnotationAiActionControls';
import {
  getDefaultAnnotationContentTab,
  type AnnotationContentTab,
} from './annotationTabs';
import {
  buildNoteUpdateData,
  getAnnotationAiExplanation,
  getAnnotationAiParaphrase,
  getAnnotationUserNote,
} from './annotationContent';
import {
  AnnotationAiExplanationLoading,
  AnnotationAiExplanationView,
} from './AnnotationAiExplanation';
import { useAnnotationExplain } from './useAnnotationExplain';
import { useAnnotationParaphrase } from './useAnnotationParaphrase';
import { getParaphraseLevelLabel } from './paraphraseLevels';

interface AnnotationDetailDrawerProps {
  annotation: Annotation | null;
  pdfId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AnnotationDetailDrawer({
  annotation,
  pdfId,
  open,
  onOpenChange,
}: AnnotationDetailDrawerProps) {
  const userNote = useMemo(
    () => (annotation ? getAnnotationUserNote(annotation) : ''),
    [annotation],
  );
  const aiExplanation = useMemo(
    () => (annotation ? getAnnotationAiExplanation(annotation) : null),
    [annotation],
  );
  const aiParaphrase = useMemo(
    () => (annotation ? getAnnotationAiParaphrase(annotation) : null),
    [annotation],
  );
  const [activeTab, setActiveTab] = useState<AnnotationContentTab>('note');
  const [isEditingNote, setIsEditingNote] = useState(false);
  const [draftNote, setDraftNote] = useState(userNote);
  const [paraphraseLevel, setParaphraseLevel] = useState<ParaphraseLevel>('same');
  const previousAnnotationIdRef = useRef<string | null>(null);
  const { mutate: updateAnnotation, isPending: isSavingNote } = useUpdateAnnotation();
  const annotationExplain = useAnnotationExplain({
    onSuccess: () => {
      setActiveTab('explanation');
    },
  });
  const annotationParaphrase = useAnnotationParaphrase({
    onSuccess: () => {
      setActiveTab('paraphrase');
    },
  });

  const isHighlightAnnotation = annotation?.type === 'highlight';
  const hasSelectedText = !!annotation?.selected_text;
  const canShowAiActions = isHighlightAnnotation && !!pdfId;
  const canUseAiActions = canShowAiActions && hasSelectedText;
  const aiUnavailableTitle = canUseAiActions
    ? undefined
    : 'No selected text for this annotation';
  const isExplainingThis =
    annotationExplain.isExplaining && annotationExplain.explainingId === annotation?.id;
  const isParaphrasingThis =
    annotationParaphrase.isParaphrasing &&
    annotationParaphrase.paraphrasingId === annotation?.id;

  /* eslint-disable react-hooks/set-state-in-effect -- Sync drawer defaults when switching annotations */
  useEffect(() => {
    if (!annotation) {
      previousAnnotationIdRef.current = null;
      return;
    }
    if (previousAnnotationIdRef.current === annotation.id) return;

    previousAnnotationIdRef.current = annotation.id;
    setDraftNote(userNote);
    setIsEditingNote(false);
    setActiveTab(
      getDefaultAnnotationContentTab(userNote, !!aiExplanation, !!aiParaphrase),
    );
  }, [annotation, aiExplanation, aiParaphrase, userNote]);

  useEffect(() => {
    if (!isEditingNote) setDraftNote(userNote);
  }, [isEditingNote, userNote]);
  /* eslint-enable react-hooks/set-state-in-effect */

  if (!annotation) return null;

  const handleSaveNote = () => {
    updateAnnotation(
      {
        id: annotation.id,
        data: buildNoteUpdateData(annotation, draftNote),
      },
      {
        onSuccess: () => {
          setIsEditingNote(false);
        },
      },
    );
  };

  const handleExplain = () => {
    if (!pdfId || !canUseAiActions) return;
    setActiveTab('explanation');
    annotationExplain.explain(annotation, pdfId);
  };

  const handleParaphrase = () => {
    if (!pdfId || !canUseAiActions) return;
    setActiveTab('paraphrase');
    annotationParaphrase.paraphrase(annotation, pdfId, paraphraseLevel);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="left-auto right-0 top-0 h-screen w-[min(92vw,32rem)] max-w-none translate-x-0 translate-y-0 gap-0 overflow-hidden rounded-none border-l p-0 sm:rounded-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="text-base">Annotation</DialogTitle>
          <DialogDescription className="sr-only">
            Annotation details, note editor, AI explanation, and AI paraphrase.
          </DialogDescription>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <FileText className="h-3.5 w-3.5" />
            <span>Page {annotation.page_number}</span>
            <span>{annotation.type}</span>
          </div>
        </DialogHeader>

        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          <div className="shrink-0 border-b px-5 py-4">
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
              Annotated text
            </h3>
            <div className="max-h-44 overflow-y-auto rounded-md border bg-muted/30 p-3 text-sm leading-relaxed text-foreground">
              {annotation.selected_text || 'No selected text for this annotation.'}
            </div>
          </div>

          <Tabs
            value={activeTab}
            onValueChange={(value) => {
              const next = value as AnnotationContentTab;
              setActiveTab(next);
              if (next !== 'note') setIsEditingNote(false);
            }}
            className="flex min-h-0 flex-1 flex-col px-5 py-4"
          >
            <div className="mb-4 space-y-3">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="note">Note</TabsTrigger>
                <TabsTrigger value="explanation">Explanation</TabsTrigger>
                <TabsTrigger value="paraphrase">Paraphrase</TabsTrigger>
              </TabsList>
              <AnnotationAiActionControls
                activeTab={activeTab}
                aiUnavailableTitle={aiUnavailableTitle}
                buttonClassName="w-full sm:w-auto"
                buttonVariant="outline"
                canUseAiActions={canUseAiActions}
                explanationClassName="flex justify-end"
                hasAiExplanation={!!aiExplanation}
                hasAiParaphrase={!!aiParaphrase}
                isExplaining={isExplainingThis}
                isParaphrasing={isParaphrasingThis}
                onExplain={canShowAiActions ? handleExplain : undefined}
                onParaphrase={canShowAiActions ? handleParaphrase : undefined}
                onParaphraseLevelChange={setParaphraseLevel}
                paraphraseClassName="grid gap-2 sm:flex sm:justify-end"
                paraphraseLevel={paraphraseLevel}
                selectTriggerClassName="h-11 w-full sm:w-36"
              />
            </div>

            <TabsContent value="note" className="mt-0 min-h-0 flex-1 overflow-y-auto">
              {isEditingNote ? (
                <div className="flex h-full min-h-[16rem] flex-col gap-3">
                  <Textarea
                    value={draftNote}
                    onChange={(event) => setDraftNote(event.target.value)}
                    placeholder="Add a note…"
                    className="min-h-[14rem] flex-1 resize-none text-sm"
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setDraftNote(userNote);
                        setIsEditingNote(false);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button onClick={handleSaveNote} disabled={isSavingNote}>
                      {isSavingNote ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4" />
                      )}
                      Save
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="prose prose-sm max-w-none rounded-md border bg-background p-4 text-foreground prose-p:my-2 prose-ul:my-2 prose-li:my-0.5">
                    {userNote ? (
                      <Markdown>{userNote}</Markdown>
                    ) : (
                      <p className="text-muted-foreground">No note yet.</p>
                    )}
                  </div>
                  <Button variant="outline" onClick={() => setIsEditingNote(true)}>
                    <Pencil className="h-4 w-4" />
                    {userNote ? 'Edit note' : 'Add note'}
                  </Button>
                </div>
              )}
            </TabsContent>

            <TabsContent value="explanation" className="mt-0 min-h-0 flex-1 overflow-y-auto">
              {isExplainingThis ? (
                <AnnotationAiExplanationLoading
                  message={annotationExplain.statusMessage || 'Generating explanation…'}
                />
              ) : aiExplanation ? (
                <AnnotationAiExplanationView
                  explanation={aiExplanation}
                  showContext
                />
              ) : (
                <div className="rounded-md border bg-background p-4 text-sm text-muted-foreground">
                  No AI explanation yet.
                </div>
              )}
            </TabsContent>
            <TabsContent value="paraphrase" className="mt-0 min-h-0 flex-1 overflow-y-auto">
              {isParaphrasingThis ? (
                <AnnotationAiExplanationLoading
                  message={annotationParaphrase.statusMessage || 'Generating paraphrase…'}
                />
              ) : aiParaphrase ? (
                <AnnotationAiExplanationView
                  explanation={aiParaphrase}
                  badgeLabel="AI Paraphrase"
                  detailLabel={getParaphraseLevelLabel(aiParaphrase.level)}
                />
              ) : (
                <div className="rounded-md border bg-background p-4 text-sm text-muted-foreground">
                  No AI paraphrase yet.
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}
