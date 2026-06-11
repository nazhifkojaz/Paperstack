import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/stores/authStore';
import { LogOut } from 'lucide-react';
import { useAutoHighlightQuota } from '@/api/autoHighlight';
import { useState, useEffect } from 'react';

function useTimeUntilMidnightUTC() {
    const [remaining, setRemaining] = useState(() => msUntilMidnightUTC());

    useEffect(() => {
        const id = setInterval(() => setRemaining(msUntilMidnightUTC()), 60_000);
        return () => clearInterval(id);
    }, []);

    return remaining;
}

function msUntilMidnightUTC() {
    const now = new Date();
    const midnight = new Date(now);
    midnight.setUTCHours(24, 0, 0, 0);
    return midnight.getTime() - now.getTime();
}

function formatDuration(ms: number): string {
    const totalMin = Math.floor(ms / 60_000);
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function ResetCountdown() {
    const ms = useTimeUntilMidnightUTC();
    return (
        <p className="text-[10px] text-muted-foreground mt-0.5">
            Refreshes in {formatDuration(ms)}
        </p>
    );
}

function QuotaRow({ label, remaining, total }: { label: string; remaining: number; total: number }) {
    return (
        <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{label}</span>
            <span className={remaining === 0 ? 'text-destructive font-medium' : ''}>
                {remaining}/{total}
            </span>
        </div>
    );
}

export function UserNav() {
    const { user, logout } = useAuthStore();
    const { data: quota } = useAutoHighlightQuota(Boolean(user));

    if (!user) return null;

    const displayName = user.display_name || user.email || 'User'
    const initials = displayName
        .split(' ')
        .map((n) => n[0])
        .join('')
        .substring(0, 2)
        .toUpperCase()

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                    <Avatar className="h-8 w-8">
                        <AvatarImage src={user.avatar_url || ''} alt={displayName} />
                        <AvatarFallback>{initials}</AvatarFallback>
                    </Avatar>
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56" align="end" forceMount>
                <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1">
                        <p className="text-sm font-medium leading-none">{displayName}</p>
                        {user.email && (
                            <p className="text-xs leading-none text-muted-foreground">{user.email}</p>
                        )}
                    </div>
                </DropdownMenuLabel>
                {quota && !(quota.has_own_key && quota.openrouter_key_mode === 'byok') && (
                    <>
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel className="font-normal">
                            <div className="flex flex-col gap-1">
                                <QuotaRow label="Chat" remaining={quota.chat_remaining} total={quota.chat_total} />
                                <QuotaRow label="Explain / Paraphrase" remaining={quota.explain_paraphrase_remaining} total={quota.explain_paraphrase_total} />
                                <QuotaRow label="Quick highlight" remaining={quota.auto_highlight_quick_remaining} total={quota.auto_highlight_quick_total} />
                                <QuotaRow label="Thorough highlight" remaining={quota.auto_highlight_thorough_remaining} total={quota.auto_highlight_thorough_total} />
                                <ResetCountdown />
                            </div>
                        </DropdownMenuLabel>
                    </>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout}>
                    <LogOut className="mr-2 h-4 w-4" />
                    <span>Log out</span>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
