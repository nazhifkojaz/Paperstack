/**
 * Tests for auth store.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'

const mockUser = {
  id: 'user-1',
  email: 'test@example.com',
  display_name: 'Test User',
  avatar_url: 'https://example.com/avatar.png',
  storage_provider: 'github' as const,
}

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.getState().logout()
  })

  describe('setAuth', () => {
    it('stores user and tokens', () => {
      useAuthStore.getState().setAuth(mockUser, 'access-token', 'refresh-token')

      const state = useAuthStore.getState()
      expect(state.user).toEqual(mockUser)
      expect(state.accessToken).toBe('access-token')
      expect(state.refreshToken).toBe('refresh-token')
    })
  })

  describe('setUser', () => {
    it('updates only user data', () => {
      useAuthStore.getState().setAuth(mockUser, 'access-token', 'refresh-token')

      const updatedUser = { ...mockUser, display_name: 'New Name' }
      useAuthStore.getState().setUser(updatedUser)

      const state = useAuthStore.getState()
      expect(state.user).toEqual(updatedUser)
      expect(state.accessToken).toBe('access-token')
      expect(state.refreshToken).toBe('refresh-token')
    })
  })

  describe('logout', () => {
    it('clears all auth data', () => {
      useAuthStore.getState().setAuth(mockUser, 'access-token', 'refresh-token')
      useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.accessToken).toBeNull()
      expect(state.refreshToken).toBeNull()
    })
  })

  describe('isAuthenticated', () => {
    it('returns true when access token exists', () => {
      useAuthStore.getState().setAuth(mockUser, 'access-token', 'refresh-token')
      expect(useAuthStore.getState().isAuthenticated()).toBe(true)
    })

    it('returns false when access token is null', () => {
      expect(useAuthStore.getState().isAuthenticated()).toBe(false)
    })

    it('returns false after logout', () => {
      useAuthStore.getState().setAuth(mockUser, 'access-token', 'refresh-token')
      useAuthStore.getState().logout()
      expect(useAuthStore.getState().isAuthenticated()).toBe(false)
    })
  })
})
