import Markdown from 'react-markdown';
import { Loader2, Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { AnnotationAiExplanation } from './annotationContent';

interface AnnotationAiExplanationViewProps {
  explanation: AnnotationAiExplanation;
  badgeLabel?: string;
  detailLabel?: string | null;
  showContext?: boolean;
  className?: string;
}

interface AnnotationAiExplanationLoadingProps {
  message?: string;
  className?: string;
}

export function AnnotationAiExplanationView({
  explanation,
  badgeLabel = 'AI Explanation',
  detailLabel,
  showContext = false,
  className,
}: AnnotationAiExplanationViewProps) {
  return (
    <div className="space-y-4">
      <div
        className={cn(
          'rounded-md border border-violet-100 bg-violet-50/40 p-4',
          className,
        )}
      >
        <div className="mb-3 flex items-center gap-2 border-b border-violet-100 pb-2">
          <Sparkles className="h-4 w-4 shrink-0 text-violet-600" />
          <Badge
            variant="outline"
            className="text-xs font-medium text-violet-700 border-violet-200 bg-violet-50 hover:bg-violet-100"
          >
            {badgeLabel}
          </Badge>
          {(detailLabel || explanation.generated_at) && (
            <div className="ml-auto flex shrink-0 items-center gap-2 text-xs text-violet-400">
              {detailLabel && <span>{detailLabel}</span>}
              {explanation.generated_at && <span>{explanation.generated_at}</span>}
            </div>
          )}
        </div>
        <div className="prose prose-sm max-w-none text-foreground prose-p:my-2 prose-ul:my-2 prose-li:my-0.5">
          <Markdown>{explanation.content}</Markdown>
        </div>
      </div>

      {showContext && explanation.context_chunks && explanation.context_chunks.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">
            Context
          </h3>
          {explanation.context_chunks.map((chunk) => (
            <div
              key={chunk.chunk_id}
              className="rounded-md border bg-background p-3 text-xs leading-relaxed text-muted-foreground"
            >
              <span className="font-medium text-foreground">p.{chunk.page_number}</span>
              {' '}
              {chunk.snippet}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AnnotationAiExplanationLoading({
  message = 'Generating explanation…',
  className,
}: AnnotationAiExplanationLoadingProps) {
  return (
    <div
      className={cn(
        'space-y-3 rounded-md border border-violet-100 bg-violet-50/40 p-4',
        className,
      )}
    >
      <div className="flex items-center gap-2 text-sm text-violet-700">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>{message}</span>
      </div>
      {[0.95, 0.82, 0.68, 0.76].map((width, index) => (
        <div
          key={index}
          className="h-3 rounded bg-violet-100"
          style={{ width: `${width * 100}%` }}
        />
      ))}
    </div>
  );
}
