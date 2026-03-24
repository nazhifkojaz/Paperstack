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

const PROVIDERS = [
    { id: 'gemini' as const, label: 'Google Gemini', docsUrl: 'https://aistudio.google.com/apikey' },
    { id: 'glm' as const, label: 'Zhipu AI (GLM)', docsUrl: 'https://open.bigmodel.cn/usercenter/apikeys' },
];

export const ApiKeyDialog = ({ open, onOpenChange }: Props) => {
    const { data: quota } = useAutoHighlightQuota();
    const createKey = useCreateApiKey();
    const deleteKey = useDeleteApiKey();
    const [inputs, setInputs] = useState<Record<string, string>>({});

    const handleSave = async (provider: 'glm' | 'gemini') => {
        const key = inputs[provider];
        if (!key?.trim()) return;

        try {
            await createKey.mutateAsync({ provider, api_key: key.trim() });
            setInputs(prev => ({ ...prev, [provider]: '' }));
            toast.success(`${provider.toUpperCase()} API key saved`);
        } catch {
            toast.error('Failed to save API key');
        }
    };

    const handleDelete = async (provider: string) => {
        try {
            await deleteKey.mutateAsync(provider);
            toast.success(`${provider.toUpperCase()} API key removed`);
        } catch {
            toast.error('Failed to remove API key');
        }
    };

    const hasKey = (provider: string) => quota?.providers.includes(provider);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>API Key Management</DialogTitle>
                    <p className="text-sm text-muted-foreground">
                        Add your own API keys for unlimited auto-highlight usage
                    </p>
                </DialogHeader>

                <div className="flex flex-col gap-4">
                    {PROVIDERS.map(provider => (
                        <div key={provider.id} className="space-y-2">
                            <div className="flex items-center justify-between">
                                <label className="text-sm font-medium">{provider.label}</label>
                                <a
                                    href={provider.docsUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-blue-400 hover:underline"
                                >
                                    Get API key
                                </a>
                            </div>

                            {hasKey(provider.id) ? (
                                <div className="flex items-center gap-2">
                                    <span className="text-sm text-muted-foreground flex-1">
                                        Key configured
                                    </span>
                                    <Button
                                        variant="destructive"
                                        size="sm"
                                        onClick={() => handleDelete(provider.id)}
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
                                        value={inputs[provider.id] || ''}
                                        onChange={e => setInputs(prev => ({
                                            ...prev, [provider.id]: e.target.value,
                                        }))}
                                    />
                                    <Button
                                        size="sm"
                                        onClick={() => handleSave(provider.id)}
                                        disabled={!inputs[provider.id]?.trim() || createKey.isPending}
                                    >
                                        Save
                                    </Button>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </DialogContent>
        </Dialog>
    );
};
