import { useState } from 'react';
import { toast } from 'sonner';
import { Loader2, Sparkles, Pencil } from 'lucide-react';
import {
    useCollectionComparison,
    useBulkSummarizeCollection,
    useGeneratePdfSummary,
    useUpdatePdfSummary,
    PdfSummary,
    ComparisonRow,
} from '@/api/summaries';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';

type EditableField =
    | 'problem'
    | 'method'
    | 'dataset'
    | 'result'
    | 'contribution';

const EDITABLE_FIELDS: { label: string; key: EditableField }[] = [
    { label: 'Problem', key: 'problem' },
    { label: 'Method', key: 'method' },
    { label: 'Dataset', key: 'dataset' },
    { label: 'Result', key: 'result' },
    { label: 'Contribution', key: 'contribution' },
];

interface ComparisonMatrixProps {
    collectionId: string;
}

interface EditingCell {
    pdfId: string;
    field: EditableField;
}

function CellValue({
    row,
    field,
    onStartEdit,
}: {
    row: ComparisonRow;
    field: EditableField;
    onStartEdit: () => void;
}) {
    const summary = row.summary;
    const value = summary ? (summary[field] as string | null) : null;
    const edited = summary?.edited_fields?.includes(field);

    return (
        <div className="cursor-text min-h-[1.5rem]" onClick={onStartEdit}>
            <span>{value || '—'}</span>
            {edited && (
                <Pencil className="inline h-3 w-3 text-muted-foreground ml-1" />
            )}
        </div>
    );
}

function CellEditor({
    row,
    field,
    onCancel,
}: {
    row: ComparisonRow;
    field: EditableField;
    onCancel: () => void;
}) {
    const updateSummary = useUpdatePdfSummary();
    const currentValue = (row.summary?.[field] as string | null) ?? '';
    const [draft, setDraft] = useState(currentValue);

    const handleSave = () => {
        if (draft !== currentValue) {
            updateSummary.mutate(
                { pdfId: row.pdf_id, [field]: draft } as {
                    pdfId: string;
                } & Partial<PdfSummary>,
                { onSuccess: onCancel },
            );
        } else {
            onCancel();
        }
    };

    return (
        <div className="space-y-1">
            <Textarea
                autoFocus
                rows={3}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === 'Escape') onCancel();
                }}
                className="text-sm"
            />
            <div className="flex gap-1">
                <Button size="sm" onClick={handleSave} disabled={updateSummary.isPending}>
                    Save
                </Button>
                <Button size="sm" variant="ghost" onClick={onCancel}>
                    Cancel
                </Button>
            </div>
        </div>
    );
}

function EditableCell({
    row,
    field,
    isEditing,
    onStartEdit,
    onCancel,
}: {
    row: ComparisonRow;
    field: EditableField;
    isEditing: boolean;
    onStartEdit: () => void;
    onCancel: () => void;
}) {
    if (isEditing) {
        return <CellEditor row={row} field={field} onCancel={onCancel} />;
    }

    return (
        <CellValue row={row} field={field} onStartEdit={onStartEdit} />
    );
}

function GeneratingCell({ summary }: { summary: PdfSummary }) {
    return (
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating… {summary.progress_pct}%
        </div>
    );
}

function MissingCell({ row }: { row: ComparisonRow }) {
    const generateSummary = useGeneratePdfSummary();
    const summary = row.summary;
    const failed = summary?.status === 'failed';

    return (
        <div className="space-y-1">
            <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">No summary</span>
                <Button
                    size="sm"
                    variant="outline"
                    className="gap-1"
                    onClick={() => generateSummary.mutate(row.pdf_id)}
                    disabled={generateSummary.isPending}
                >
                    {generateSummary.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                        <Sparkles className="h-3 w-3" />
                    )}
                    Generate
                </Button>
            </div>
            {failed && summary?.error_message && (
                <p className="text-xs text-destructive">{summary.error_message}</p>
            )}
        </div>
    );
}

export function ComparisonMatrix({ collectionId }: ComparisonMatrixProps) {
    const { data: comparison, isLoading } = useCollectionComparison(collectionId);
    const bulkSummarize = useBulkSummarizeCollection();
    const [editing, setEditing] = useState<EditingCell | null>(null);

    const missingCount = comparison?.missing_count ?? 0;
    const rowCount = comparison?.rows.length ?? 0;

    const handleGenerateMissing = () => {
        if (!collectionId) return;
        bulkSummarize.mutate(collectionId, {
            onSuccess: (data) => {
                if (data.skipped_quota > 0) {
                    toast.info(
                        `${data.skipped_quota} paper(s) skipped — daily summary quota reached.`,
                    );
                }
            },
        });
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-primary/50" />
            </div>
        );
    }

    if (rowCount === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <p className="text-sm">No papers in this collection yet.</p>
            </div>
        );
    }

    return (
        <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                    {rowCount} paper{rowCount === 1 ? '' : 's'} ·{' '}
                    {missingCount} without summar
                    {missingCount === 1 ? 'y' : 'ies'}
                </p>
                <Button
                    size="sm"
                    variant="outline"
                    className="gap-1"
                    onClick={handleGenerateMissing}
                    disabled={missingCount === 0 || bulkSummarize.isPending}
                >
                    <Sparkles className="h-3 w-3" />
                    Generate missing ({missingCount})
                </Button>
            </div>

            <div className="border rounded-lg overflow-auto max-h-[70vh]">
                <Table>
                    <TableHeader>
                        <TableRow className="sticky top-0 bg-card z-20">
                            <TableHead className="sticky left-0 bg-card z-10 min-w-[220px]">
                                Paper
                            </TableHead>
                            <TableHead>Year</TableHead>
                            {EDITABLE_FIELDS.map(({ label, key }) => (
                                <TableHead key={key}>{label}</TableHead>
                            ))}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {comparison!.rows.map((row) => {
                            const summary = row.summary;
                            const generating = summary?.status === 'generating';
                            const complete = summary?.status === 'complete';

                            return (
                                <TableRow key={row.pdf_id}>
                                    <TableCell
                                        className="sticky left-0 bg-card z-10 align-top"
                                        style={{ minWidth: 220 }}
                                    >
                                        <span className="line-clamp-2 text-sm font-medium">
                                            {row.title}
                                        </span>
                                    </TableCell>
                                    <TableCell className="align-top text-sm">
                                        {row.year ?? '—'}
                                    </TableCell>
                                    {generating ? (
                                        <TableCell
                                            colSpan={EDITABLE_FIELDS.length}
                                            className="align-top"
                                        >
                                            <GeneratingCell summary={summary!} />
                                        </TableCell>
                                    ) : !complete ? (
                                        <TableCell
                                            colSpan={EDITABLE_FIELDS.length}
                                            className="align-top"
                                        >
                                            <MissingCell row={row} />
                                        </TableCell>
                                    ) : (
                                        EDITABLE_FIELDS.map(({ key }) => {
                                            const isEditing =
                                                editing?.pdfId === row.pdf_id &&
                                                editing?.field === key;
                                            return (
                                                <TableCell
                                                    key={key}
                                                    className="align-top min-w-[200px]"
                                                >
                                                    <EditableCell
                                                        row={row}
                                                        field={key}
                                                        isEditing={isEditing}
                                                        onStartEdit={() =>
                                                            setEditing({
                                                                pdfId: row.pdf_id,
                                                                field: key,
                                                            })
                                                        }
                                                        onCancel={() =>
                                                            setEditing(null)
                                                        }
                                                    />
                                                </TableCell>
                                            );
                                        })
                                    )}
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
