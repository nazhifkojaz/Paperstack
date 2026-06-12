import { FileText, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface LibraryEmptyStateProps {
  onAddPdf: () => void;
  searchQuery?: string;
}

export function LibraryEmptyState({
  onAddPdf,
  searchQuery,
}: LibraryEmptyStateProps) {
  if (searchQuery) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center min-h-[300px]">
        <div className="flex items-center justify-center w-16 h-16 mb-4 rounded-full bg-muted/50 text-muted-foreground">
          <FileText className="w-8 h-8" />
        </div>
        <h3 className="text-lg font-semibold mb-2">No PDFs found</h3>
        <p className="text-sm text-muted-foreground mb-6 max-w-xs">
          We couldn't find anything matching "{searchQuery}".
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center min-h-[300px]">
      <div className="flex items-center justify-center w-16 h-16 mb-4 rounded-full bg-primary/10 text-primary">
        <FileText className="w-8 h-8" />
      </div>
      <h3 className="text-lg font-semibold mb-2">Your library is empty</h3>
      <p className="text-sm text-muted-foreground mb-8 max-w-sm">
        Upload your first paper to start annotating, chatting, and citing with ease.
      </p>

      <Button onClick={onAddPdf} className="gap-2">
        <Plus className="w-4 h-4" />
        Upload PDF
      </Button>

      <div className="mt-8 p-4 rounded-lg bg-muted/50 border max-w-sm text-left space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Pro tip</p>
        <p className="text-sm text-muted-foreground">
          You can also drag & drop PDFs directly onto this page, or use the "Link" option to reference papers hosted elsewhere.
        </p>
      </div>
    </div>
  );
}
