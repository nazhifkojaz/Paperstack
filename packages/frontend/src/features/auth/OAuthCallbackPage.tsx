import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { apiFetch } from '@/api/client'
import type { User } from '@/stores/authStore'


export function OAuthCallbackPage() {
    const navigate = useNavigate()
    const setAuth = useAuthStore((s) => s.setAuth)

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

        // Temporarily set token so the api client can fetch /auth/me
        useAuthStore.setState({ accessToken, refreshToken })

        apiFetch<User>('/auth/me')
            .then((user) => {
                setAuth(user, accessToken, refreshToken)
                navigate('/library', { replace: true })
            })
            .catch(() => {
                navigate('/login', { replace: true })
            })
    }, [navigate, setAuth])

    return (
        <div className="min-h-screen flex items-center justify-center bg-background">
            <div className="flex flex-col items-center gap-4">
                <div className="text-3xl animate-pulse">📄</div>
                <p className="text-muted-foreground text-sm">Signing you in…</p>
            </div>
        </div>
    )
}
