import { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';

interface GlobalQuotaWarningProps {
    message?: string | null;
}

export function GlobalQuotaWarning({ message }: GlobalQuotaWarningProps) {
    const [dismissedMessage, setDismissedMessage] = useState<string | null>(null);

    useEffect(() => {
        if (message && message !== dismissedMessage) {
            setDismissedMessage(null);
        }
    }, [message, dismissedMessage]);

    if (!message || dismissedMessage === message) return null;

    return (
        <div className="mt-2 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-2.5 py-2 text-left text-xs text-amber-900">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 flex-1">{message}</span>
            <button
                type="button"
                className="shrink-0 rounded p-0.5 text-amber-900/70 hover:bg-amber-100 hover:text-amber-950"
                onClick={() => setDismissedMessage(message)}
                aria-label="Dismiss warning"
            >
                <X className="h-3.5 w-3.5" />
            </button>
        </div>
    );
}
