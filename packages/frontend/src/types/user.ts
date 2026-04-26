export interface User {
    id: string
    email?: string
    display_name?: string
    avatar_url?: string
    storage_provider: 'github' | 'google'
}
