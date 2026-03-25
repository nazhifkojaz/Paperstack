import { useAuthStore } from '@/stores/authStore'
import { API_URL, BASE_URL } from '@/lib/config'

class ApiError extends Error {
    constructor(
        public status: number,
        public code: string,
        message: string,
    ) {
        super(message)
        this.name = 'ApiError'
    }
}

/**
 * Parses an error response body into a structured error.
 * Returns default values if the response is not JSON or parsing fails.
 */
async function parseErrorBody(res: Response): Promise<{ detail: string; code: string }> {
    try {
        const err = await res.json()
        return {
            detail: err.detail ?? 'Request failed',
            code: err.code ?? 'unknown',
        }
    } catch {
        return { detail: 'Request failed', code: 'unknown' }
    }
}

/**
 * Handles 401 unauthorized responses by attempting to refresh the access token.
 * Returns true if refresh succeeded, false if it failed (triggers logout).
 */
async function handleUnauthorized(): Promise<boolean> {
    const { refreshToken, setAuth, user, logout } = useAuthStore.getState()
    if (!refreshToken) {
        logout()
        return false
    }

    try {
        const res = await fetch(`${API_URL}/auth/refresh`, {
            method: 'POST',
            // Content-Type header auto-added by fetch for JSON.stringify() body
            body: JSON.stringify({ refresh_token: refreshToken }),
        })

        if (!res.ok) {
            logout()
            return false
        }

        const data = await res.json()
        if (user) {
            setAuth(user, data.access_token, data.refresh_token ?? refreshToken)
        }
        return true
    } catch {
        logout()
        return false
    }
}

/**
 * Higher-order function that wraps an API call with 401 refresh logic.
 * If the call returns 401, attempts refresh once and retries.
 *
 * @param fetchFn - The fetch function to execute
 * @param retry - Whether this is a retry attempt (prevents infinite loops)
 * @returns The parsed response or throws ApiError
 */
async function withAuthRefresh<T>(
    fetchFn: () => Promise<Response>,
    retry = true,
): Promise<Response> {
    const res = await fetchFn()

    // Handle 401 with refresh token flow
    if (res.status === 401 && retry) {
        const refreshed = await handleUnauthorized()
        if (refreshed) {
            // Retry the request with new token
            return withAuthRefresh<T>(fetchFn, false)
        } else {
            // Refresh failed - logout and redirect
            window.location.href = `${BASE_URL}/login`
            throw new ApiError(401, 'unauthorized', 'Session expired. Please log in again.')
        }
    }

    return res
}

export async function apiFetch<T>(
    path: string,
    options: RequestInit & { authRequired?: boolean } = {},
): Promise<T> {
    const { accessToken } = useAuthStore.getState()
    const { authRequired = true, ...fetchOptions } = options

    const isFormData = fetchOptions.body instanceof FormData
    const headers: Record<string, string> = {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(fetchOptions.headers as Record<string, string>),
    }

    if (authRequired && accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
    }

    const res = await withAuthRefresh<T>(() =>
        fetch(`${API_URL}${path}`, { ...fetchOptions, headers })
    )

    if (!res.ok) {
        const { detail, code } = await parseErrorBody(res)
        throw new ApiError(res.status, code, detail)
    }

    // Handle empty responses (204 No Content)
    if (res.status === 204) return undefined as T

    return res.json() as Promise<T>
}


export async function apiFetchBlob(
    path: string,
    options: RequestInit = {},
): Promise<Blob> {
    const { accessToken } = useAuthStore.getState()

    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string>),
    }

    if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
    }

    const res = await withAuthRefresh<Blob>(() =>
        fetch(`${API_URL}${path}`, { ...options, headers })
    )

    if (!res.ok) {
        const { detail, code } = await parseErrorBody(res)
        throw new ApiError(res.status, code, detail)
    }

    return res.blob()
}

export { ApiError }
