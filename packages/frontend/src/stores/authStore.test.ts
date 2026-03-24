/**
 * Tests for auth store.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'

describe('authStore', () => {
  beforeEach(() => {
    // Reset store before each test
    useAuthStore.getState().logout()
  })

  describe('setAuth', () => {
    it('stores user and tokens', () => {
      const user = {
        id: 'user-1',
        github_id: 123456,
        github_login: 'testuser',
        display_name: 'Test User',
        avatar_url: 'https://example.com/avatar.png',
        repo_created: false,
      }

      useAuthStore.getState().setAuth(user, 'access-token', 'refresh-token')

      const state = useAuthStore.getState()
      expect(state.user).toEqual(user)
      expect(state.accessToken).toBe('access-token')
      expect(state.refreshToken).toBe('refresh-token')
    })
  })

  describe('setUser', () => {
    it('updates only user data', () => {
      const user = {
        id: 'user-1',
        github_id: 123456,
        github_login: 'testuser',
        repo_created: false,
      }

      useAuthStore.getState().setAuth(user, 'access-token', 'refresh-token')

      const updatedUser = {
        id: 'user-1',
        github_id: 123456,
        github_login: 'newlogin',
        display_name: 'New Name',
        avatar_url: 'https://example.com/new.png',
        repo_created: true,
      }

      useAuthStore.getState().setUser(updatedUser)

      const state = useAuthStore.getState()
      expect(state.user).toEqual(updatedUser)
      expect(state.accessToken).toBe('access-token')
      expect(state.refreshToken).toBe('refresh-token')
    })
  })

  describe('logout', () => {
    it('clears all auth data', () => {
      const user = {
        id: 'user-1',
        github_id: 123456,
        github_login: 'testuser',
        repo_created: false,
      }

      useAuthStore.getState().setAuth(user, 'access-token', 'refresh-token')
      useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.accessToken).toBeNull()
      expect(state.refreshToken).toBeNull()
    })
  })

  describe('isAuthenticated', () => {
    it('returns true when access token exists', () => {
      useAuthStore.getState().setAuth(
        {
          id: 'user-1',
          github_id: 123456,
          github_login: 'testuser',
          repo_created: false,
        },
        'access-token',
        'refresh-token'
      )

      expect(useAuthStore.getState().isAuthenticated()).toBe(true)
    })

    it('returns false when access token is null', () => {
      expect(useAuthStore.getState().isAuthenticated()).toBe(false)
    })

    it('returns false after logout', () => {
      useAuthStore.getState().setAuth(
        {
          id: 'user-1',
          github_id: 123456,
          github_login: 'testuser',
          repo_created: false,
        },
        'access-token',
        'refresh-token'
      )

      useAuthStore.getState().logout()
      expect(useAuthStore.getState().isAuthenticated()).toBe(false)
    })
  })
})
