import { AlertCircle, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ErrorBoundaryFallbackProps {
    error: Error;
    resetErrorBoundary: () => void;
}

export function ErrorBoundaryFallback({ error, resetErrorBoundary }: ErrorBoundaryFallbackProps) {
    return (
        <div className="flex flex-col items-center justify-center min-h-[400px] w-full p-6 text-center bg-background border rounded-lg shadow-sm">
            <div className="flex items-center justify-center w-12 h-12 mb-4 rounded-full bg-destructive/10">
                <AlertCircle className="w-6 h-6 text-destructive" />
            </div>
            <h2 className="text-xl font-semibold tracking-tight text-foreground mb-2">Something went wrong</h2>
            <p className="max-w-md mb-6 text-sm text-muted-foreground">
                An unexpected error occurred. You can try refreshing the page or clicking the button below to reset.
            </p>

            {process.env.NODE_ENV === 'development' && (
                <pre className="w-full max-w-2xl p-4 mb-6 text-xs text-left overflow-auto rounded bg-muted/50 text-destructive border border-destructive/20 max-h-[200px]">
                    {error.message}
                    {error.stack}
                </pre>
            )}

            <div className="flex gap-4">
                <Button
                    variant="outline"
                    onClick={() => window.location.reload()}
                    className="gap-2"
                >
                    <RefreshCcw className="w-4 h-4" />
                    Refresh Page
                </Button>
                <Button
                    onClick={resetErrorBoundary}
                    className="gap-2"
                >
                    Try again
                </Button>
            </div>
        </div>
    );
}
