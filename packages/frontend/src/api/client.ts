import { useAuthStore } from '@/stores/authStore'

const API_URL = import.meta.env?.VITE_API_URL ?? '/v1'

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

async function refreshAccessToken(): Promise<string | null> {
    const { refreshToken, setAuth, user, logout } = useAuthStore.getState()
    if (!refreshToken) return null

    try {
        const res = await fetch(`${API_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!res.ok) {
            logout()
            return null
        }
        const data = await res.json()
        if (user) {
            setAuth(user, data.access_token, data.refresh_token ?? refreshToken)
        }
        return data.access_token
    } catch {
        logout()
        return null
    }
}

export async function apiFetch<T>(
    path: string,
    options: RequestInit & { authRequired?: boolean } = {},
    retry = true,
): Promise<T> {
    const { accessToken, logout } = useAuthStore.getState()
    const { authRequired = true, ...fetchOptions } = options

    const isFormData = fetchOptions.body instanceof FormData
    const headers: Record<string, string> = {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(fetchOptions.headers as Record<string, string>),
    }

    if (authRequired && accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
    }

    const res = await fetch(`${API_URL}${path}`, { ...fetchOptions, headers })

    if (authRequired && res.status === 401 && retry) {
        const newToken = await refreshAccessToken()
        if (newToken) {
            return apiFetch<T>(path, options, false)
        } else {
            logout()
            window.location.href = '/Paperstack/login'
            throw new ApiError(401, 'unauthorized', 'Session expired. Please log in again.')
        }
    }

    if (!res.ok) {
        let detail = 'Request failed'
        let code = 'unknown'
        try {
            const err = await res.json()
            detail = err.detail ?? detail
            code = err.code ?? code
        } catch { }
        throw new ApiError(res.status, code, detail)
    }

    // Handle empty responses (204 No Content)
    if (res.status === 204) return undefined as T

    return res.json() as Promise<T>
}


export async function apiFetchBlob(
    path: string,
    options: RequestInit = {},
    retry = true,
): Promise<Blob> {
    const { accessToken, logout } = useAuthStore.getState()

    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string>),
    }

    if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
    }

    const res = await fetch(`${API_URL}${path}`, { ...options, headers })

    if (res.status === 401 && retry) {
        const newToken = await refreshAccessToken()
        if (newToken) {
            return apiFetchBlob(path, options, false)
        } else {
            logout()
            window.location.href = '/Paperstack/login'
            throw new ApiError(401, 'unauthorized', 'Session expired. Please log in again.')
        }
    }

    if (!res.ok) {
        let detail = 'Request failed'
        let code = 'unknown'
        try {
            const err = await res.json()
            detail = err.detail ?? detail
            code = err.code ?? code
        } catch { }
        throw new ApiError(res.status, code, detail)
    }

    return res.blob()
}

export const api = {
    get: <T>(path: string, options?: RequestInit) =>
        apiFetch<T>(path, { method: 'GET', ...options }),

    post: <T>(path: string, body?: unknown, options?: RequestInit) =>
        apiFetch<T>(path, {
            method: 'POST',
            body: body !== undefined ? JSON.stringify(body) : undefined,
            ...options,
        }),

    patch: <T>(path: string, body?: unknown, options?: RequestInit) =>
        apiFetch<T>(path, {
            method: 'PATCH',
            body: body !== undefined ? JSON.stringify(body) : undefined,
            ...options,
        }),

    put: <T>(path: string, body?: unknown, options?: RequestInit) =>
        apiFetch<T>(path, {
            method: 'PUT',
            body: body !== undefined ? JSON.stringify(body) : undefined,
            ...options,
        }),

    delete: <T>(path: string, options?: RequestInit) =>
        apiFetch<T>(path, { method: 'DELETE', ...options }),

    /** For multipart/form-data uploads — do not set Content-Type header */
    upload: <T>(path: string, formData: FormData, options?: RequestInit) => {
        const { accessToken } = useAuthStore.getState()
        const headers: Record<string, string> = {}
        if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`
        return apiFetch<T>(path, {
            method: 'POST',
            body: formData,
            headers,
            ...options,
        })
    },
}

export { ApiError }
