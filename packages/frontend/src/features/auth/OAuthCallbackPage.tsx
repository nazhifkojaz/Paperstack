import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { API_URL } from '@/lib/config'
import type { User } from '@/stores/authStore'


export function OAuthCallbackPage() {
    const navigate = useNavigate()
    const setAuth = useAuthStore((s) => s.setAuth)
    const logout = useAuthStore((s) => s.logout)

    useEffect(() => {
        // Parse tokens from URL fragment (hash) instead of query params
        // Fragments are not sent to server and don't appear in logs/history
        const parseHashParams = (hash: string): Record<string, string> => {
            const params: Record<string, string> = {}
            // Remove the leading # and split by &
            const pairs = hash.substring(1).split('&')
            for (const pair of pairs) {
                const [key, value] = pair.split('=')
                if (key && value) {
                    params[key] = value
                }
            }
            return params
        }

        const params = parseHashParams(window.location.hash)
        const accessToken = params['access_token']
        const refreshToken = params['refresh_token']

        if (!accessToken || !refreshToken) {
            navigate('/login', { replace: true })
            return
        }

        // Verify tokens with /auth/me BEFORE persisting to store
        // This prevents polluting the store with invalid tokens
        fetch(`${API_URL}/auth/me`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json',
            },
        })
            .then((res) => {
                if (!res.ok) {
                    throw new Error('Authentication failed')
                }
                return res.json() as Promise<User>
            })
            .then((user) => {
                // Only persist to store after successful verification
                setAuth(user, accessToken, refreshToken)
                navigate('/library', { replace: true })
            })
            .catch(() => {
                // Clear any potentially invalid state and redirect to login
                logout()
                navigate('/login', { replace: true })
            })
    }, [navigate, setAuth, logout])

    return (
        <div className="min-h-screen flex items-center justify-center bg-background">
            <div className="flex flex-col items-center gap-4">
                <div className="text-3xl animate-pulse">📄</div>
                <p className="text-muted-foreground text-sm">Signing you in…</p>
            </div>
        </div>
    )
}
