import { AlertCircle, RefreshCw } from 'lucide-react';

interface ChatIndexErrorBannerProps {
  error: string | null;
  isSending: boolean;
  onRetry: () => void;
}

export function ChatIndexErrorBanner({
  error,
  isSending,
  onRetry,
}: ChatIndexErrorBannerProps) {
  if (!error) return null;

  return (
    <div className="mx-3 mt-2 flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive shrink-0">
      <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="font-medium">Indexing failed</p>
        <p className="text-destructive/80 mt-0.5 break-words">{error}</p>
      </div>
      <button
        onClick={onRetry}
        disabled={isSending}
        className="flex items-center gap-1 text-xs font-medium text-destructive hover:text-destructive/80 disabled:opacity-50 shrink-0"
        title="Retry indexing"
      >
        <RefreshCw className="h-3 w-3" />
        Retry
      </button>
    </div>
  );
}
