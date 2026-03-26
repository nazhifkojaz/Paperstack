import { useState } from 'react';
import { useCreateShare, useRevokeShare, Share } from '@/api/sharing';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Copy, Check, Trash2, Link, UserPlus, Loader2 } from 'lucide-react';
import { buildUrl } from '@/lib/config';

interface ShareDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    setId: string;
    setName: string;
    existingShares: Share[];
}

export const ShareDialog = ({
    open,
    onOpenChange,
    setId,
    setName,
    existingShares,
}: ShareDialogProps) => {
    const [githubLogin, setGithubLogin] = useState('');
    const [permission, setPermission] = useState<'view' | 'comment'>('view');
    const [copiedToken, setCopiedToken] = useState<string | null>(null);

    const createShare = useCreateShare(setId);
    const revokeShare = useRevokeShare();

    const handleCreatePublicLink = () => {
        createShare.mutate({ permission });
    };

    const handleShareWithUser = () => {
        if (!githubLogin.trim()) return;
        createShare.mutate(
            { shared_with_github_login: githubLogin.trim(), permission },
            { onSuccess: () => setGithubLogin('') }
        );
    };

    const handleCopy = (token: string) => {
        const url = `${window.location.origin}${buildUrl(`/shared/${token}`)}`;
        navigator.clipboard.writeText(url);
        setCopiedToken(token);
        setTimeout(() => setCopiedToken(null), 2000);
    };

    const handleRevoke = (shareId: string) => {
        revokeShare.mutate(shareId);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle>Share "{setName}"</DialogTitle>
                </DialogHeader>

                <div className="space-y-5">
                    {/* Permission selector */}
                    <div className="space-y-1.5">
                        <Label>Permission</Label>
                        <Select
                            value={permission}
                            onValueChange={(v: 'view' | 'comment') => setPermission(v)}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="view">View only</SelectItem>
                                <SelectItem value="comment">Can comment</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Public link */}
                    <div className="space-y-2">
                        <Label>Public link</Label>
                        <Button
                            variant="outline"
                            className="w-full gap-2"
                            onClick={handleCreatePublicLink}
                            disabled={createShare.isPending}
                        >
                            {createShare.isPending
                                ? <Loader2 className="h-4 w-4 animate-spin" />
                                : <Link className="h-4 w-4" />}
                            Generate link
                        </Button>
                    </div>

                    {/* Share with specific user */}
                    <div className="space-y-2">
                        <Label>Share with user</Label>
                        <div className="flex gap-2">
                            <Input
                                placeholder="GitHub username"
                                value={githubLogin}
                                onChange={(e) => setGithubLogin(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleShareWithUser()}
                            />
                            <Button
                                size="icon"
                                onClick={handleShareWithUser}
                                disabled={createShare.isPending || !githubLogin.trim()}
                            >
                                {createShare.isPending
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <UserPlus className="h-4 w-4" />}
                            </Button>
                        </div>
                        {createShare.isError && (
                            <p className="text-xs text-destructive">{(createShare.error as Error).message}</p>
                        )}
                    </div>

                    {/* Active shares */}
                    {existingShares.length > 0 && (
                        <div className="space-y-2">
                            <Label>Active shares</Label>
                            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                                {existingShares.map((share) => (
                                    <div
                                        key={share.id}
                                        className="flex items-center gap-2 p-2 rounded-md border text-sm"
                                    >
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs text-muted-foreground truncate">
                                                {share.shared_with
                                                    ? `User: ${share.shared_with_github_login || 'Unknown'}`
                                                    : 'Public link'}
                                            </p>
                                            <p className="text-xs capitalize text-primary">{share.permission}</p>
                                        </div>

                                        {!share.shared_with && (
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-7 w-7 shrink-0"
                                                onClick={() => handleCopy(share.share_token)}
                                            >
                                                {copiedToken === share.share_token
                                                    ? <Check className="h-3.5 w-3.5 text-green-500" />
                                                    : <Copy className="h-3.5 w-3.5" />}
                                            </Button>
                                        )}

                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
                                            onClick={() => handleRevoke(share.id)}
                                            disabled={revokeShare.isPending}
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
};
