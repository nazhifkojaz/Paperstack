import { apiFetch } from './client'
import { User } from '@/stores/authStore'

export async function updateStorageProvider(provider: 'github' | 'google'): Promise<User> {
    return apiFetch<User>('/settings/storage-provider', {
        method: 'PATCH',
        body: JSON.stringify({ storage_provider: provider }),
    })
}

interface ConnectedAccount {
    provider: string
    display_name: string
}

export async function fetchConnectedAccounts(): Promise<ConnectedAccount[]> {
    const res = await apiFetch<{ accounts: ConnectedAccount[] }>('/settings/connected-accounts')
    return res.accounts
}

// --- LLM model preferences ---

export interface LLMModel {
    id: string
    label: string
    description: string
}

export interface LLMPreferences {
    chat_model: string | null
    auto_highlight_model: string | null
    explain_model: string | null
}

export type LLMPreferencesUpdate = Partial<Record<keyof LLMPreferences, string | null>>

export async function fetchLLMModels(): Promise<LLMModel[]> {
    const res = await apiFetch<{ models: LLMModel[] }>('/settings/llm-models')
    return res.models
}

export async function fetchLLMPreferences(): Promise<LLMPreferences> {
    return apiFetch<LLMPreferences>('/settings/llm-preferences')
}

export async function updateLLMPreferences(data: LLMPreferencesUpdate): Promise<LLMPreferences> {
    return apiFetch<LLMPreferences>('/settings/llm-preferences', {
        method: 'PATCH',
        body: JSON.stringify(data),
    })
}
