import { useState, useEffect } from 'react'
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { updateStorageProvider, fetchConnectedAccounts } from '@/api/settings'
import { toast } from 'sonner'

interface Props {
    open: boolean
    onOpenChange: (open: boolean) => void
}

const PROVIDERS = [
    {
        id: 'google' as const,
        label: 'Google Drive',
        description: 'PDFs stored in a Paperstack folder in your Google Drive.',
    },
    {
        id: 'github' as const,
        label: 'GitHub',
        description: 'PDFs stored in a private pdfbuddy-library repository.',
    },
]

export function StorageSettingsDialog({ open, onOpenChange }: Props) {
    const { user, setUser } = useAuthStore()
    const [loading, setLoading] = useState(false)
    const [connectedProviders, setConnectedProviders] = useState<Set<string>>(new Set())

    useEffect(() => {
        if (!open) return
        fetchConnectedAccounts()
            .then((accounts) => {
                setConnectedProviders(new Set(accounts.map((a) => a.provider)))
            })
            .catch(() => {
                toast.error('Failed to load connected accounts')
            })
    }, [open])

    const handleSwitch = async (provider: 'github' | 'google') => {
        if (!user || provider === user.storage_provider) return
        setLoading(true)
        try {
            const updated = await updateStorageProvider(provider)
            setUser({ ...user, storage_provider: updated.storage_provider })
            toast.success(`Storage switched to ${provider === 'google' ? 'Google Drive' : 'GitHub'}`)
            onOpenChange(false)
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Failed to switch storage'
            toast.error(msg)
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Storage Settings</DialogTitle>
                    <p className="text-sm text-muted-foreground">
                        Choose where new PDFs are stored. Existing PDFs are not moved.
                    </p>
                </DialogHeader>

                <div className="flex flex-col gap-3 pt-2">
                    {PROVIDERS.map((p) => {
                        const isActive = user?.storage_provider === p.id
                        const isConnected = connectedProviders.has(p.id)
                        return (
                            <div
                                key={p.id}
                                className={`flex items-center justify-between rounded-lg border p-3 ${
                                    isActive ? 'border-primary bg-primary/5' : 'border-border'
                                }`}
                            >
                                <div className="space-y-0.5">
                                    <p className="text-sm font-medium">{p.label}</p>
                                    <p className="text-xs text-muted-foreground">{p.description}</p>
                                </div>
                                {isActive ? (
                                    <span className="text-xs font-medium text-primary">Active</span>
                                ) : isConnected ? (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        disabled={loading}
                                        onClick={() => handleSwitch(p.id)}
                                    >
                                        Switch
                                    </Button>
                                ) : (
                                    <span className="text-xs text-muted-foreground">
                                        Not connected
                                    </span>
                                )}
                            </div>
                        )
                    })}
                </div>
            </DialogContent>
        </Dialog>
    )
}
