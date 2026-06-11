import { useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useCreateApiKey, useDeleteApiKey, useAutoHighlightQuota } from '@/api/autoHighlight';
import { toast } from 'sonner';

interface Props {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export const ApiKeyDialog = ({ open, onOpenChange }: Props) => {
    const { data: quota } = useAutoHighlightQuota();
    const createKey = useCreateApiKey();
    const deleteKey = useDeleteApiKey();
    const [keyInput, setKeyInput] = useState('');

    const handleSave = async () => {
        if (!keyInput.trim()) return;

        try {
            await createKey.mutateAsync({ provider: 'openrouter', api_key: keyInput.trim() });
            setKeyInput('');
            toast.success('OpenRouter API key saved');
        } catch {
            toast.error('Failed to save API key');
        }
    };

    const handleDelete = async () => {
        try {
            await deleteKey.mutateAsync('openrouter');
            toast.success('OpenRouter API key removed');
        } catch {
            toast.error('Failed to remove API key');
        }
    };

    const hasKey = quota?.providers.includes('openrouter') ?? false;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>API Key Management</DialogTitle>
                    <p className="text-sm text-muted-foreground">
                        Add your OpenRouter API key for BYOK models and unlimited AI usage
                    </p>
                </DialogHeader>

                <div className="flex flex-col gap-4">
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-medium">OpenRouter</label>
                            <a
                                href="https://openrouter.ai/settings/keys"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-blue-400 hover:underline"
                            >
                                Get API key
                            </a>
                        </div>

                        {hasKey ? (
                            <div className="flex items-center gap-2">
                                <span className="text-sm text-muted-foreground flex-1">
                                    Key configured
                                </span>
                                <Button
                                    variant="destructive"
                                    size="sm"
                                    onClick={handleDelete}
                                    disabled={deleteKey.isPending}
                                >
                                    Remove
                                </Button>
                            </div>
                        ) : (
                            <div className="flex gap-2">
                                <Input
                                    type="password"
                                    placeholder="Enter API key..."
                                    value={keyInput}
                                    onChange={e => setKeyInput(e.target.value)}
                                />
                                <Button
                                    size="sm"
                                    onClick={handleSave}
                                    disabled={!keyInput.trim() || createKey.isPending}
                                >
                                    Save
                                </Button>
                            </div>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};
