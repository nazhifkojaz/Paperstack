import { useState, useEffect, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import Markdown from 'react-markdown';
import { useUpdateAnnotation, type Annotation } from '@/api/annotations';
import type { ParaphraseLevel } from '@/api/chat';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Pencil, Save } from 'lucide-react';
import { AnnotationAiActionControls } from './AnnotationAiActionControls';
import {
    getDefaultAnnotationContentTab,
    type AnnotationContentTab,
} from './annotationTabs';
import {
    AnnotationAiExplanationLoading,
    AnnotationAiExplanationView,
} from './AnnotationAiExplanation';
import {
    buildNoteUpdateData,
    getAnnotationAiExplanation,
    getAnnotationAiParaphrase,
    getAnnotationUserNote,
} from './annotationContent';
import { getParaphraseLevelLabel } from './paraphraseLevels';

const PREFERRED_CARD_WIDTH = 384;
const CARD_MAX_HEIGHT = 420;
const CARD_MIN_HEIGHT = 96;
const EDGE_MARGIN = 8;
const ANCHOR_GAP = 8;

interface NotePopoverProps {
    annotation: Annotation;
    containerDims: { width: number; height: number } | null;
    containerElement?: HTMLElement | null;
    onClose: () => void;
    isExplaining?: boolean;
    explainStatusMessage?: string;
    onExplainThis?: (annotationId: string) => void;
    isParaphrasing?: boolean;
    paraphraseStatusMessage?: string;
    onParaphraseThis?: (annotationId: string, level?: ParaphraseLevel) => void;
}

function clamp(value: number, min: number, max: number): number {
    if (max < min) return min;
    return Math.min(Math.max(value, min), max);
}

function getCardWidth(availableWidth: number): number {
    return Math.max(0, Math.min(PREFERRED_CARD_WIDTH, availableWidth - EDGE_MARGIN * 2));
}

function getAnnotationBounds(rects: Annotation['rects']) {
    const minX = Math.min(...rects.map((r) => r.x));
    const minY = Math.min(...rects.map((r) => r.y));
    const maxX = Math.max(...rects.map((r) => r.x + r.w));
    const maxY = Math.max(...rects.map((r) => r.y + r.h));
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

export const NotePopover = ({
    annotation,
    containerDims,
    containerElement,
    onClose,
    isExplaining,
    explainStatusMessage,
    onExplainThis,
    isParaphrasing,
    paraphraseStatusMessage,
    onParaphraseThis,
}: NotePopoverProps) => {
    const userNote = useMemo(() => getAnnotationUserNote(annotation), [annotation]);
    const aiExplanation = useMemo(() => getAnnotationAiExplanation(annotation), [annotation]);
    const aiParaphrase = useMemo(() => getAnnotationAiParaphrase(annotation), [annotation]);
    const hasAiExplanation = !!aiExplanation || !!isExplaining;
    const hasAiParaphrase = !!aiParaphrase || !!isParaphrasing;
    const hasAiContent = hasAiExplanation || hasAiParaphrase;
    const canShowAiActions = annotation.type === 'highlight' && (!!onExplainThis || !!onParaphraseThis);
    const canUseAiActions = canShowAiActions && !!annotation.selected_text;
    const hasTabbedContent = hasAiContent || canShowAiActions;
    const aiUnavailableTitle = canUseAiActions
        ? undefined
        : 'No selected text for this annotation';
    const [content, setContent] = useState(userNote);
    const [isEditing, setIsEditing] = useState(!userNote && !hasAiContent);
    const [activeTab, setActiveTab] = useState<AnnotationContentTab>(
        getDefaultAnnotationContentTab(
            userNote,
            hasAiExplanation,
            hasAiParaphrase,
        ),
    );
    const [paraphraseLevel, setParaphraseLevel] = useState<ParaphraseLevel>('same');
    const prevIsExplainingRef = useRef(isExplaining ?? false);
    const prevIsParaphrasingRef = useRef(isParaphrasing ?? false);

    /* eslint-disable react-hooks/set-state-in-effect -- Sync while/after explain generation */
    useEffect(() => {
        if (isExplaining) {
            setContent(userNote);
            setIsEditing(false);
            setActiveTab('explanation');
        } else if (prevIsExplainingRef.current) {
            setContent(userNote);
            setIsEditing(false);
            setActiveTab('explanation');
        }
        prevIsExplainingRef.current = isExplaining ?? false;
    }, [isExplaining, userNote]);
    /* eslint-enable react-hooks/set-state-in-effect */

    /* eslint-disable react-hooks/set-state-in-effect -- Sync while/after paraphrase generation */
    useEffect(() => {
        if (isParaphrasing) {
            setContent(userNote);
            setIsEditing(false);
            setActiveTab('paraphrase');
        } else if (prevIsParaphrasingRef.current) {
            setContent(userNote);
            setIsEditing(false);
            setActiveTab('paraphrase');
        }
        prevIsParaphrasingRef.current = isParaphrasing ?? false;
    }, [isParaphrasing, userNote]);
    /* eslint-enable react-hooks/set-state-in-effect */

    /* eslint-disable react-hooks/set-state-in-effect -- Keep local editor state aligned when annotation changes */
    useEffect(() => {
        if (isEditing) return;
        setContent(userNote);
        if (activeTab === 'note' && !userNote && !hasAiContent) setIsEditing(true);
    }, [activeTab, annotation.id, hasAiContent, isEditing, userNote]);
    /* eslint-enable react-hooks/set-state-in-effect */

    const { mutate: updateAnnotation } = useUpdateAnnotation();
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const popoverRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (isEditing) {
            textareaRef.current?.focus();
        }
    }, [isEditing]);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (popoverRef.current?.contains(target)) return;
            if (target.closest('[data-radix-popper-content-wrapper]')) return;
            onClose();
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [onClose]);

    const handleSave = () => {
        updateAnnotation({
            id: annotation.id,
            data: buildNoteUpdateData(annotation, content),
        });
        onClose();
    };

    const handleCancel = () => {
        setContent(userNote);
        if (userNote || hasAiContent) {
            setIsEditing(false);
        } else {
            onClose();
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            onClose();
        }
    };

    const handleExplain = () => {
        if (!canUseAiActions || !onExplainThis) return;
        setActiveTab('explanation');
        setIsEditing(false);
        onExplainThis(annotation.id);
    };

    const handleParaphrase = () => {
        if (!canUseAiActions || !onParaphraseThis) return;
        setActiveTab('paraphrase');
        setIsEditing(false);
        onParaphraseThis(annotation.id, paraphraseLevel);
    };

    if (!containerDims || !annotation.rects[0]) return null;

    const rect = getAnnotationBounds(annotation.rects);
    const viewportPosition = containerElement
        ? getViewportPosition(rect, containerElement)
        : null;
    const fallbackPosition = getContainerPosition(rect, containerDims);
    const position = viewportPosition ?? fallbackPosition;

    const isAiTab = activeTab !== 'note' && hasTabbedContent;
    const isAiContent = isAiTab && !isExplaining && !isParaphrasing;

    const noteContent = isEditing ? (
        <div className="p-3">
            <Textarea
                ref={textareaRef}
                placeholder="Add a note…"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                onKeyDown={handleKeyDown}
                className="min-h-[100px] resize-none text-sm border-0 focus-visible:ring-1 focus-visible:ring-violet-400 bg-transparent shadow-none"
            />
        </div>
    ) : userNote ? (
        <div className="p-4">
            <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 text-gray-800 leading-relaxed">
                <Markdown>{userNote}</Markdown>
            </div>
        </div>
    ) : (
        <div className="p-4 text-sm text-muted-foreground">
            No note yet.
        </div>
    );

    const explanationContent = isExplaining ? (
        <AnnotationAiExplanationLoading
            message={explainStatusMessage || 'Generating explanation…'}
            className="rounded-none border-0 bg-transparent"
        />
    ) : aiExplanation ? (
        <AnnotationAiExplanationView
            explanation={aiExplanation}
            className="rounded-none border-0 bg-transparent"
        />
    ) : (
        <div className="p-4 text-sm text-muted-foreground">
            No AI explanation yet.
        </div>
    );

    const paraphraseContent = isParaphrasing ? (
        <AnnotationAiExplanationLoading
            message={paraphraseStatusMessage || 'Generating paraphrase…'}
            className="rounded-none border-0 bg-transparent"
        />
    ) : aiParaphrase ? (
        <AnnotationAiExplanationView
            explanation={aiParaphrase}
            badgeLabel="AI Paraphrase"
            detailLabel={getParaphraseLevelLabel(aiParaphrase.level)}
            enableCopy
            className="rounded-none border-0 bg-transparent"
        />
    ) : (
        <div className="p-4 text-sm text-muted-foreground">
            No AI paraphrase yet.
        </div>
    );

    const popover = (
        <div
            ref={popoverRef}
            className={`${position.mode === 'fixed' ? 'fixed' : 'absolute'} z-50 pointer-events-auto`}
            style={position.style}
            onClick={(e) => e.stopPropagation()}
            data-testid="note-popover-root"
        >
            <div
                className={`rounded-xl shadow-2xl border flex flex-col ${
                    isAiContent
                        ? 'bg-violet-50/95 border-violet-200'
                        : 'bg-white border-gray-200'
                }`}
                style={{ width: `${position.cardWidth}px`, maxHeight: `${position.maxHeight}px` }}
                data-testid="note-popover-card"
            >
                {/* Scrollable content */}
                <div className="flex-1 min-h-0 overflow-y-auto">
                    {hasTabbedContent ? (
                        <Tabs
                            value={activeTab}
                            onValueChange={(value) => {
                                const next = value as AnnotationContentTab;
                                setActiveTab(next);
                                if (next !== 'note') setIsEditing(false);
                            }}
                            className="p-3"
                        >
                            <TabsList className="grid w-full grid-cols-3">
                                <TabsTrigger value="note">Note</TabsTrigger>
                                <TabsTrigger value="explanation">Explanation</TabsTrigger>
                                <TabsTrigger value="paraphrase">Paraphrase</TabsTrigger>
                            </TabsList>
                            <TabsContent value="note" className="mt-3 rounded-md border border-gray-100">
                                {noteContent}
                            </TabsContent>
                            <TabsContent value="explanation" className="mt-3 rounded-md border border-violet-100 bg-violet-50/30">
                                {explanationContent}
                            </TabsContent>
                            <TabsContent value="paraphrase" className="mt-3 rounded-md border border-violet-100 bg-violet-50/30">
                                {paraphraseContent}
                            </TabsContent>
                        </Tabs>
                    ) : (
                        noteContent
                    )}
                </div>

                {/* Sticky footer */}
                <div
                    className={`shrink-0 border-t px-3 py-2.5 flex flex-wrap items-center justify-end gap-2 ${
                        isAiContent
                            ? 'border-violet-100 bg-violet-50/60'
                            : 'border-gray-100 bg-white/80 backdrop-blur-sm'
                    }`}
                >
                    {isEditing && activeTab === 'note' ? (
                        <>
                            <Button size="sm" variant="ghost" onClick={handleCancel}>
                                Cancel
                            </Button>
                            <Button size="sm" onClick={handleSave}>
                                <Save className="h-3 w-3 mr-1" />
                                Save
                            </Button>
                        </>
                    ) : activeTab === 'explanation' && onExplainThis ? (
                        <>
                            <Button size="sm" variant="ghost" onClick={onClose}>
                                Close
                            </Button>
                            <AnnotationAiActionControls
                                activeTab={activeTab}
                                aiUnavailableTitle={aiUnavailableTitle}
                                canUseAiActions={canUseAiActions}
                                explanationClassName="contents"
                                hasAiExplanation={!!aiExplanation}
                                hasAiParaphrase={!!aiParaphrase}
                                iconClassName="h-3 w-3"
                                isExplaining={!!isExplaining}
                                isParaphrasing={!!isParaphrasing}
                                onExplain={handleExplain}
                                onParaphraseLevelChange={setParaphraseLevel}
                                paraphraseLevel={paraphraseLevel}
                            />
                        </>
                    ) : activeTab === 'paraphrase' && onParaphraseThis ? (
                        <>
                            <Button size="sm" variant="ghost" onClick={onClose}>
                                Close
                            </Button>
                            <AnnotationAiActionControls
                                activeTab={activeTab}
                                aiUnavailableTitle={aiUnavailableTitle}
                                canUseAiActions={canUseAiActions}
                                hasAiExplanation={!!aiExplanation}
                                hasAiParaphrase={!!aiParaphrase}
                                iconClassName="h-3 w-3"
                                isExplaining={!!isExplaining}
                                isParaphrasing={!!isParaphrasing}
                                onParaphrase={handleParaphrase}
                                onParaphraseLevelChange={setParaphraseLevel}
                                paraphraseClassName="contents"
                                paraphraseLevel={paraphraseLevel}
                                selectTriggerClassName="h-11 w-32"
                            />
                        </>
                    ) : (
                        <>
                            <Button size="sm" variant="ghost" onClick={onClose}>
                                Close
                            </Button>
                            {activeTab === 'note' && (
                                <Button size="sm" onClick={() => {
                                    setActiveTab('note');
                                    setIsEditing(true);
                                }}>
                                    <Pencil className="h-3 w-3 mr-1" />
                                    Edit Note
                                </Button>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );

    return position.mode === 'fixed' ? createPortal(popover, document.body) : popover;
};

function getContainerPosition(
    rect: { x: number; y: number; w: number; h: number },
    containerDims: { width: number; height: number },
) {
    const centerX = (rect.x + rect.w / 2) * containerDims.width;
    const cardWidth = getCardWidth(containerDims.width);
    const left = clamp(centerX - cardWidth / 2, EDGE_MARGIN, containerDims.width - cardWidth - EDGE_MARGIN);
    const annotationBottomY = (rect.y + rect.h) * containerDims.height;
    const annotationTopY = rect.y * containerDims.height;
    const spaceBelow = containerDims.height - annotationBottomY - EDGE_MARGIN - ANCHOR_GAP;
    const spaceAbove = annotationTopY - EDGE_MARGIN - ANCHOR_GAP;
    const showAbove = spaceBelow < CARD_MAX_HEIGHT && spaceAbove > spaceBelow;
    const availableHeight = Math.max(CARD_MIN_HEIGHT, showAbove ? spaceAbove : spaceBelow);
    const maxHeight = Math.min(CARD_MAX_HEIGHT, availableHeight);

    return {
        mode: 'absolute' as const,
        cardWidth,
        maxHeight,
        style: {
            left: `${left}px`,
            top: `${showAbove ? annotationTopY - ANCHOR_GAP : annotationBottomY + ANCHOR_GAP}px`,
            transform: showAbove ? 'translateY(-100%)' : 'none',
        },
    };
}

function getViewportPosition(
    rect: { x: number; y: number; w: number; h: number },
    containerElement: HTMLElement,
) {
    const containerRect = containerElement.getBoundingClientRect();
    if (containerRect.width <= 0 || containerRect.height <= 0) return null;

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const cardWidth = getCardWidth(viewportWidth);
    const anchorCenterX = containerRect.left + (rect.x + rect.w / 2) * containerRect.width;
    const anchorTopY = containerRect.top + rect.y * containerRect.height;
    const anchorBottomY = containerRect.top + (rect.y + rect.h) * containerRect.height;
    const spaceBelow = viewportHeight - anchorBottomY - EDGE_MARGIN - ANCHOR_GAP;
    const spaceAbove = anchorTopY - EDGE_MARGIN - ANCHOR_GAP;
    const showAbove = spaceBelow < CARD_MAX_HEIGHT && spaceAbove > spaceBelow;
    const availableHeight = Math.max(CARD_MIN_HEIGHT, showAbove ? spaceAbove : spaceBelow);
    const maxHeight = Math.min(CARD_MAX_HEIGHT, availableHeight);

    return {
        mode: 'fixed' as const,
        cardWidth,
        maxHeight,
        style: {
            left: `${clamp(anchorCenterX - cardWidth / 2, EDGE_MARGIN, viewportWidth - cardWidth - EDGE_MARGIN)}px`,
            top: `${showAbove ? anchorTopY - ANCHOR_GAP : anchorBottomY + ANCHOR_GAP}px`,
            transform: showAbove ? 'translateY(-100%)' : 'none',
        },
    };
}
