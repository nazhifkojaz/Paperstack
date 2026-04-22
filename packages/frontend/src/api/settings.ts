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
