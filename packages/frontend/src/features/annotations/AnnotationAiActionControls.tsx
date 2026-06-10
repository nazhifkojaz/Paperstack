import type { ComponentProps } from 'react';
import { Loader2, RefreshCw, Sparkles } from 'lucide-react';
import type { ParaphraseLevel } from '@/api/chat';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { AnnotationContentTab } from './annotationTabs';
import { PARAPHRASE_LEVELS } from './paraphraseLevels';

type ButtonVariant = ComponentProps<typeof Button>['variant'];
type ButtonSize = ComponentProps<typeof Button>['size'];

interface AnnotationAiActionControlsProps {
  activeTab: AnnotationContentTab;
  aiUnavailableTitle?: string;
  buttonClassName?: string;
  buttonSize?: ButtonSize;
  buttonVariant?: ButtonVariant;
  canUseAiActions: boolean;
  explanationClassName?: string;
  hasAiExplanation: boolean;
  hasAiParaphrase: boolean;
  iconClassName?: string;
  isExplaining: boolean;
  isParaphrasing: boolean;
  onExplain?: () => void;
  onParaphrase?: () => void;
  onParaphraseLevelChange: (level: ParaphraseLevel) => void;
  paraphraseClassName?: string;
  paraphraseLevel: ParaphraseLevel;
  selectTriggerClassName?: string;
}

export function AnnotationAiActionControls({
  activeTab,
  aiUnavailableTitle,
  buttonClassName,
  buttonSize = 'sm',
  buttonVariant,
  canUseAiActions,
  explanationClassName = 'flex justify-end',
  hasAiExplanation,
  hasAiParaphrase,
  iconClassName = 'h-4 w-4',
  isExplaining,
  isParaphrasing,
  onExplain,
  onParaphrase,
  onParaphraseLevelChange,
  paraphraseClassName = 'grid gap-2',
  paraphraseLevel,
  selectTriggerClassName = 'h-11 w-full',
}: AnnotationAiActionControlsProps) {
  if (activeTab === 'explanation' && onExplain) {
    return (
      <div className={explanationClassName}>
        <Button
          size={buttonSize}
          variant={buttonVariant}
          className={buttonClassName}
          onClick={onExplain}
          disabled={isExplaining || !canUseAiActions}
          title={aiUnavailableTitle}
        >
          {isExplaining ? (
            <Loader2 className={`${iconClassName} animate-spin`} />
          ) : (
            <Sparkles className={iconClassName} />
          )}
          {hasAiExplanation ? 'Re-explain' : 'Explain this'}
        </Button>
      </div>
    );
  }

  if (activeTab === 'paraphrase' && onParaphrase) {
    return (
      <div className={paraphraseClassName}>
        <Select
          value={paraphraseLevel}
          onValueChange={(value) => onParaphraseLevelChange(value as ParaphraseLevel)}
          disabled={isParaphrasing || !canUseAiActions}
        >
          <SelectTrigger className={selectTriggerClassName}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PARAPHRASE_LEVELS.map((level) => (
              <SelectItem key={level.value} value={level.value}>
                {level.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size={buttonSize}
          variant={buttonVariant}
          className={buttonClassName}
          onClick={onParaphrase}
          disabled={isParaphrasing || !canUseAiActions}
          title={aiUnavailableTitle}
        >
          {isParaphrasing ? (
            <Loader2 className={`${iconClassName} animate-spin`} />
          ) : (
            <RefreshCw className={iconClassName} />
          )}
          {hasAiParaphrase ? 'Rephrase' : 'Paraphrase this'}
        </Button>
      </div>
    );
  }

  return null;
}
