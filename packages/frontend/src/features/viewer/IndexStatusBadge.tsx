import { useIndexStatus, useReindexPdf } from '@/api/indexStatus';
import { Badge } from '@/components/ui/badge';
import { Loader2, Database, AlertCircle, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

interface IndexStatusBadgeProps {
    pdfId: string;
}

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
    not_indexed: { label: 'Not indexed', className: 'text-muted-foreground bg-muted' },
    indexing: { label: 'Indexing...', className: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950' },
    indexed: { label: 'Indexed', className: 'text-green-700 bg-green-50 dark:text-green-400 dark:bg-green-950' },
    failed: { label: 'Indexing failed', className: 'text-destructive bg-destructive/10' },
};

export function IndexStatusBadge({ pdfId }: IndexStatusBadgeProps) {
    const { data, isLoading } = useIndexStatus(pdfId);
    const reindex = useReindexPdf(pdfId);

    if (isLoading || !data) return null;

    const config = STATUS_CONFIG[data.status] ?? STATUS_CONFIG.not_indexed;

    const tooltip = data.status === 'indexed'
        ? `${data.chunk_count ?? 0} chunks indexed${data.indexed_at ? ` at ${new Date(data.indexed_at).toLocaleString()}` : ''}`
        : data.status === 'failed'
          ? data.error_message ?? 'Indexing failed'
          : config.label;

    return (
        <div className="flex items-center gap-1.5" title={tooltip}>
            <Badge
                variant="outline"
                className={cn('text-xs gap-1 font-normal cursor-default', config.className)}
            >
                {data.status === 'indexing' && <Loader2 className="h-3 w-3 animate-spin" />}
                {data.status === 'indexed' && <Database className="h-3 w-3" />}
                {data.status === 'failed' && <AlertCircle className="h-3 w-3" />}
                {config.label}
            </Badge>
            {(data.status === 'not_indexed' || data.status === 'failed') && (
                <button
                    onClick={() => reindex.mutate()}
                    disabled={reindex.isPending}
                    className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                    title={data.status === 'failed' ? 'Retry indexing' : 'Start indexing'}
                >
                    <RefreshCw className={cn('h-3 w-3', reindex.isPending && 'animate-spin')} />
                </button>
            )}
        </div>
    );
}
