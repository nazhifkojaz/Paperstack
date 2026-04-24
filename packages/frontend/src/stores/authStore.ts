import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '@/types/user'

export type { User }

interface AuthState {
    user: User | null
    accessToken: string | null
    refreshToken: string | null
    setAuth: (user: User, accessToken: string, refreshToken: string) => void
    setUser: (user: User) => void
    logout: () => void
    isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set, get) => ({
            user: null,
            accessToken: null,
            refreshToken: null,

            setAuth: (user, accessToken, refreshToken) =>
                set({ user, accessToken, refreshToken }),

            setUser: (user) => set({ user }),

            logout: () =>
                set({ user: null, accessToken: null, refreshToken: null }),

            isAuthenticated: () => {
                const { accessToken } = get()
                return !!accessToken
            },
        }),
        {
            name: 'paperstack-auth',
            partialize: (state) => ({
                user: state.user,
                accessToken: state.accessToken,
                refreshToken: state.refreshToken,
            }),
        },
    ),
)
