import React from 'react';
import { FileText, Search, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface EmptyStateProps {
    icon?: React.ReactNode;
    title: string;
    description: string;
    actionLabel?: string;
    onAction?: () => void;
}

export function EmptyState({
    icon,
    title,
    description,
    actionLabel,
    onAction
}: EmptyStateProps) {
    return (
        <div className="flex flex-col items-center justify-center p-8 text-center min-h-[300px]">
            <div className="flex items-center justify-center w-16 h-16 mb-4 rounded-full bg-muted/50 text-muted-foreground">
                {icon || <FileText className="w-8 h-8" />}
            </div>
            <h3 className="text-lg font-semibold mb-2">{title}</h3>
            <p className="text-sm text-muted-foreground mb-6 max-w-xs">{description}</p>
            {actionLabel && onAction && (
                <Button onClick={onAction} className="gap-2">
                    <Plus className="w-4 h-4" />
                    {actionLabel}
                </Button>
            )}
        </div>
    );
}

export function LibraryEmptyState({ onUpload }: { onUpload: () => void }) {
    return (
        <EmptyState
            title="No PDFs yet"
            description="Upload your first PDF to start organizing and annotating your research library."
            actionLabel="Upload PDF"
            onAction={onUpload}
        />
    );
}

export function SearchEmptyState({ query }: { query: string }) {
    return (
        <EmptyState
            icon={<Search className="w-8 h-8" />}
            title="No results found"
            description={`We couldn't find anything matching "${query}". Try a different search term or clear filters.`}
        />
    );
}
