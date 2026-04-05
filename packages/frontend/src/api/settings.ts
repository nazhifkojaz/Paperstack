import { apiFetch } from './client'
import { User } from '@/stores/authStore'

export async function updateStorageProvider(provider: 'github' | 'google'): Promise<User> {
    return apiFetch<User>('/settings/storage-provider', {
        method: 'PATCH',
        body: JSON.stringify({ storage_provider: provider }),
    })
}
