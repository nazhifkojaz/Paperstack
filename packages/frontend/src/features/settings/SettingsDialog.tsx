import { useState, useEffect, useCallback } from 'react'
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useAuthStore } from '@/stores/authStore'
import {
    updateStorageProvider, fetchConnectedAccounts,
    fetchLLMModels, fetchLLMPreferences, updateLLMPreferences,
} from '@/api/settings'
import type { LLMModel, LLMPreferencesUpdate } from '@/api/settings'
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
        description: 'PDFs stored in a private paperstack-library repository.',
    },
]

type FeatureKey = 'chat_model' | 'auto_highlight_model' | 'explain_model'

const FEATURE_LABELS: Record<FeatureKey, string> = {
    chat_model: 'Chat',
    auto_highlight_model: 'Auto-highlight',
    explain_model: 'Explain',
}

export function SettingsDialog({ open, onOpenChange }: Props) {
    const { user, setUser } = useAuthStore()
    const [loading, setLoading] = useState(false)

    // Storage state
    const [connectedProviders, setConnectedProviders] = useState<Set<string>>(new Set())

    // LLM state
    const [models, setModels] = useState<LLMModel[]>([])
    const [preferences, setPreferences] = useState<Record<FeatureKey, string | null>>({
        chat_model: null,
        auto_highlight_model: null,
        explain_model: null,
    })

    useEffect(() => {
        if (!open) return

        fetchConnectedAccounts()
            .then((accounts) => setConnectedProviders(new Set(accounts.map((a) => a.provider))))
            .catch(() => toast.error('Failed to load connected accounts'))

        fetchLLMModels()
            .then(setModels)
            .catch(() => toast.error('Failed to load available models'))

        fetchLLMPreferences()
            .then((prefs) =>
                setPreferences({
                    chat_model: prefs.chat_model,
                    auto_highlight_model: prefs.auto_highlight_model,
                    explain_model: prefs.explain_model,
                }),
            )
            .catch(() => toast.error('Failed to load model preferences'))
    }, [open])

    const handleStorageSwitch = async (provider: 'github' | 'google') => {
        if (!user || provider === user.storage_provider) return
        setLoading(true)
        try {
            const updated = await updateStorageProvider(provider)
            setUser({ ...user, storage_provider: updated.storage_provider })
            toast.success(`Storage switched to ${provider === 'google' ? 'Google Drive' : 'GitHub'}`)
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Failed to switch storage'
            toast.error(msg)
        } finally {
            setLoading(false)
        }
    }

    const handleModelChange = useCallback(
        async (feature: FeatureKey, value: string) => {
            const modelId = value === '__auto__' ? null : value
            setPreferences((prev) => ({ ...prev, [feature]: modelId }))

            try {
                await updateLLMPreferences({ [feature]: modelId } as LLMPreferencesUpdate)
                toast.success(`${FEATURE_LABELS[feature]} model updated`)
            } catch {
                toast.error(`Failed to update ${FEATURE_LABELS[feature]} model`)
                setPreferences((prev) => ({ ...prev, [feature]: modelId === null ? preferences[feature] : null }))
            }
        },
        [preferences],
    )

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>Settings</DialogTitle>
                </DialogHeader>

                {/* Storage section */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium">Storage</h3>
                    <p className="text-xs text-muted-foreground">
                        Choose where new PDFs are stored. Existing PDFs are not moved.
                    </p>
                    <div className="flex flex-col gap-2">
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
                                            onClick={() => handleStorageSwitch(p.id)}
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
                </div>

                <Separator />

                {/* LLM model section */}
                <div className="space-y-3">
                    <div>
                        <h3 className="text-sm font-medium">AI Models</h3>
                        <p className="text-xs text-muted-foreground mt-1">
                            Select a free OpenRouter model per feature. Choosing a model forces
                            the free tier for that feature, even if you have API keys configured.
                        </p>
                    </div>

                    <div className="flex flex-col gap-3">
                        {(Object.keys(FEATURE_LABELS) as FeatureKey[]).map((feature) => (
                            <div key={feature} className="space-y-1">
                                <label className="text-xs font-medium text-muted-foreground">
                                    {FEATURE_LABELS[feature]}
                                </label>
                                <Select
                                    value={preferences[feature] ?? '__auto__'}
                                    onValueChange={(v) => handleModelChange(feature, v)}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__auto__">Auto (use API keys first)</SelectItem>
                                        {models.map((m) => (
                                            <SelectItem key={m.id} value={m.id}>
                                                {m.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        ))}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
