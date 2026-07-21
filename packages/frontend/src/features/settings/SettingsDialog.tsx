import { useState, useEffect, useCallback, useMemo } from 'react'
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { useAuthStore } from '@/stores/authStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import {
    updateStorageProvider, fetchConnectedAccounts,
    fetchLLMModels, fetchLLMPreferences, updateLLMPreferences,
} from '@/api/settings'
import { useAutoHighlightQuota, useCreateApiKey, useDeleteApiKey } from '@/api/autoHighlight'
import type { LLMModel, LLMPreferencesUpdate } from '@/api/settings'
import { toast } from 'sonner'
import { SettingsOnboardingModal } from '@/features/onboarding/SettingsOnboardingModal'

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

type FeatureKey = 'conversation_model' | 'analysis_model'
type OpenRouterKeyMode = 'app' | 'byok'
type PreferenceState = Record<FeatureKey, string | null> & {
    openrouter_key_mode: OpenRouterKeyMode
}

const FEATURE_LABELS: Record<FeatureKey, string> = {
    conversation_model: 'Conversation',
    analysis_model: 'Analysis',
}

const FEATURE_DESCRIPTIONS: Record<FeatureKey, string> = {
    conversation_model: 'Used for chat and explain (interactive)',
    analysis_model: 'Used for auto-highlight and summaries (background)',
}

export function SettingsDialog({ open, onOpenChange }: Props) {
    const { user, setUser } = useAuthStore()
    const { hasSeenSettingsOnboarding } = useOnboardingStore()
    const [showOnboarding, setShowOnboarding] = useState(false)
    const [loading, setLoading] = useState(false)

    // Show onboarding modal on first settings open
    useEffect(() => {
        if (open && !hasSeenSettingsOnboarding) {
            setShowOnboarding(true)
        }
    }, [open, hasSeenSettingsOnboarding])

    // Storage state
    const [connectedProviders, setConnectedProviders] = useState<Set<string>>(new Set())

    // OpenRouter BYOK state
    const { data: quota } = useAutoHighlightQuota(open)
    const createKey = useCreateApiKey()
    const deleteKey = useDeleteApiKey()
    const [openRouterKey, setOpenRouterKey] = useState('')
    const hasOpenRouterKey = quota?.providers.includes('openrouter') ?? false

    // LLM state
    const [models, setModels] = useState<LLMModel[]>([])
    const [preferences, setPreferences] = useState<PreferenceState>({
        conversation_model: null,
        analysis_model: null,
        openrouter_key_mode: 'app',
    })
    const byokModelIds = useMemo(
        () => new Set(models.filter((m) => m.requires_byok).map((m) => m.id)),
        [models],
    )
    const isByokMode = preferences.openrouter_key_mode === 'byok'

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
                    conversation_model: prefs.conversation_model,
                    analysis_model: prefs.analysis_model,
                    openrouter_key_mode: prefs.openrouter_key_mode,
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
            const previousModel = preferences[feature]
            setPreferences((prev) => ({ ...prev, [feature]: modelId }))

            try {
                await updateLLMPreferences({ [feature]: modelId } as LLMPreferencesUpdate)
                toast.success(`${FEATURE_LABELS[feature]} model updated`)
            } catch {
                toast.error(`Failed to update ${FEATURE_LABELS[feature]} model`)
                setPreferences((prev) => ({ ...prev, [feature]: previousModel }))
            }
        },
        [preferences],
    )

    const buildAppModeUpdate = useCallback(() => {
        const update: LLMPreferencesUpdate = { openrouter_key_mode: 'app' }
        const next: PreferenceState = { ...preferences, openrouter_key_mode: 'app' }

        for (const feature of Object.keys(FEATURE_LABELS) as FeatureKey[]) {
            const selectedModel = preferences[feature]
            if (selectedModel && byokModelIds.has(selectedModel)) {
                update[feature] = null
                next[feature] = null
            }
        }

        return { update, next }
    }, [byokModelIds, preferences])

    const handleKeyModeChange = useCallback(
        async (mode: OpenRouterKeyMode) => {
            if (mode === preferences.openrouter_key_mode) return
            if (mode === 'byok' && !hasOpenRouterKey) {
                toast.error('Add an OpenRouter API key before switching to BYOK mode')
                return
            }

            const { update, next } = mode === 'app'
                ? buildAppModeUpdate()
                : {
                    update: { openrouter_key_mode: 'byok' } as LLMPreferencesUpdate,
                    next: { ...preferences, openrouter_key_mode: 'byok' as const },
                }

            setPreferences(next)
            try {
                await updateLLMPreferences(update)
                toast.success('OpenRouter key source updated')
            } catch {
                toast.error('Failed to update OpenRouter key source')
                setPreferences(preferences)
            }
        },
        [buildAppModeUpdate, hasOpenRouterKey, preferences],
    )

    const handleSaveOpenRouterKey = async () => {
        const apiKey = openRouterKey.trim()
        if (!apiKey) return

        try {
            await createKey.mutateAsync({ provider: 'openrouter', api_key: apiKey })
            setOpenRouterKey('')
            toast.success('OpenRouter API key saved')
        } catch {
            toast.error('Failed to save OpenRouter API key')
        }
    }

    const handleDeleteOpenRouterKey = async () => {
        try {
            await deleteKey.mutateAsync('openrouter')
            if (preferences.openrouter_key_mode === 'byok') {
                const { update, next } = buildAppModeUpdate()
                await updateLLMPreferences(update)
                setPreferences(next)
            }
            toast.success('OpenRouter API key removed')
        } catch {
            toast.error('Failed to remove OpenRouter API key')
        }
    }

    return (
        <>
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
                            App key mode supports free models. BYOK mode uses
                            your OpenRouter key for every LLM request.
                        </p>
                    </div>

                    <div className="space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">
                            Key source
                        </label>
                        <div className="grid grid-cols-2 gap-1 rounded-md border border-border p-1">
                            <Button
                                type="button"
                                variant={isByokMode ? 'ghost' : 'secondary'}
                                size="sm"
                                onClick={() => handleKeyModeChange('app')}
                            >
                                App key
                            </Button>
                            <Button
                                type="button"
                                variant={isByokMode ? 'secondary' : 'ghost'}
                                size="sm"
                                onClick={() => handleKeyModeChange('byok')}
                                disabled={!hasOpenRouterKey}
                            >
                                BYOK key
                            </Button>
                        </div>
                    </div>

                    <div className="flex flex-col gap-3">
                        {(Object.keys(FEATURE_LABELS) as FeatureKey[]).map((feature) => (
                            <div key={feature} className="space-y-1">
                                <label className="text-xs font-medium text-muted-foreground">
                                    {FEATURE_LABELS[feature]}
                                </label>
                                <p className="text-[10px] text-muted-foreground/80 -mt-0.5">
                                    {FEATURE_DESCRIPTIONS[feature]}
                                </p>
                                <Select
                                    value={preferences[feature] ?? '__auto__'}
                                    onValueChange={(v) => handleModelChange(feature, v)}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="max-h-72">
                                        <SelectItem value="__auto__">Auto (default model)</SelectItem>
                                        {models.map((m) => {
                                            const disabled = m.requires_byok && !isByokMode
                                            return (
                                                <SelectItem key={m.id} value={m.id} disabled={disabled}>
                                                    {m.label}{m.requires_byok ? ' (BYOK)' : ''}
                                                </SelectItem>
                                            )
                                        })}
                                    </SelectContent>
                                </Select>
                            </div>
                        ))}
                    </div>
                </div>

                <Separator />

                {/* OpenRouter BYOK section */}
                <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <h3 className="text-sm font-medium">OpenRouter API Key</h3>
                            <p className="text-xs text-muted-foreground mt-1">
                                BYOK mode uses this key for every LLM call. Embeddings try it
                                first and fall back to the app key when quota or balance is unavailable.
                            </p>
                        </div>
                        <a
                            href="https://openrouter.ai/settings/keys"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="shrink-0 text-xs text-blue-400 hover:underline"
                        >
                            Get API key
                        </a>
                    </div>

                    {hasOpenRouterKey ? (
                        <div className="flex items-center justify-between rounded-lg border border-border p-3">
                            <span className="text-sm text-muted-foreground">Key configured</span>
                            <Button
                                variant="destructive"
                                size="sm"
                                onClick={handleDeleteOpenRouterKey}
                                disabled={deleteKey.isPending}
                            >
                                Remove
                            </Button>
                        </div>
                    ) : (
                        <div className="flex gap-2">
                            <Input
                                type="password"
                                placeholder="Enter OpenRouter API key..."
                                value={openRouterKey}
                                onChange={(e) => setOpenRouterKey(e.target.value)}
                            />
                            <Button
                                size="sm"
                                onClick={handleSaveOpenRouterKey}
                                disabled={!openRouterKey.trim() || createKey.isPending}
                            >
                                Save
                            </Button>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>

        <SettingsOnboardingModal
            open={showOnboarding}
            onOpenChange={(open) => {
                setShowOnboarding(open)
            }}
        />
        </>
    )
}
