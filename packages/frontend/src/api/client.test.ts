/**
 * Tests for API client.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, apiFetchBlob, api, ApiError } from './client'
import { useAuthStore } from '@/stores/authStore'

// Mock fetch
const mockFetch = vi.fn<typeof global.fetch>()
global.fetch = mockFetch

// Mock window.location
const mockLocation = { href: '' }
Object.defineProperty(window, 'location', {
  value: mockLocation,
  writable: true,
})

describe('apiFetch', () => {
  beforeEach(() => {
    // Reset auth store before each test
    useAuthStore.getState().logout()
    mockFetch.mockClear()
    mockLocation.href = ''
  })

  describe('authorization header injection', () => {
    it('includes authorization header when token exists', async () => {
      useAuthStore.getState().setAuth(
        { id: '1', github_id: 1, github_login: 'test', repo_created: false },
        'test-token',
        'refresh-token'
      )

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: 'test' }),
        status: 200,
      } as Response)

      await apiFetch('/test', { method: 'GET' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      )
    })

    it('does not include authorization header when authRequired is false', async () => {
      useAuthStore.getState().setAuth(
        { id: '1', github_id: 1, github_login: 'test', repo_created: false },
        'test-token',
        'refresh-token'
      )

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: 'test' }),
        status: 200,
      } as Response)

      await apiFetch('/test', { authRequired: false })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.not.objectContaining({
            Authorization: expect.any(String),
          }),
        })
      )
    })
  })

  describe('401 retry with token refresh', () => {
    it('retries with new token on 401', async () => {
      // Set up initial auth state
      useAuthStore.getState().setAuth(
        { id: '1', github_id: 1, github_login: 'test', repo_created: false },
        'expired-token',
        'valid-refresh-token'
      )

      // First call returns 401, second succeeds
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Unauthorized' }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ access_token: 'new-token', refresh_token: 'new-refresh' }),
          status: 200,
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ data: 'success' }),
          status: 200,
        } as Response)

      const result = await apiFetch('/test')

      expect(mockFetch).toHaveBeenCalledTimes(3) // Initial, refresh, retry
      expect(result).toEqual({ data: 'success' })
      expect(useAuthStore.getState().accessToken).toBe('new-token')
    })

    it('only retries once to prevent infinite loops', async () => {
      useAuthStore.getState().setAuth(
        { id: '1', github_id: 1, github_login: 'test', repo_created: false },
        'expired-token',
        'valid-refresh-token'
      )

      // Both calls return 401
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Unauthorized' }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ access_token: 'new-token' }),
          status: 200,
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Unauthorized' }),
        } as Response)

      await expect(apiFetch('/test')).rejects.toThrow(ApiError)
      expect(mockFetch).toHaveBeenCalledTimes(3) // Should not retry again
    })

    it('logs out and redirects on failed refresh', async () => {
      useAuthStore.getState().setAuth(
        { id: '1', github_id: 1, github_login: 'test', repo_created: false },
        'expired-token',
        'invalid-refresh-token'
      )

      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Unauthorized' }),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Invalid refresh token' }),
        } as Response)

      await expect(apiFetch('/test')).rejects.toThrow(ApiError)
      expect(useAuthStore.getState().accessToken).toBeNull()
      expect(mockLocation.href).toContain('/login')
    })
  })

  describe('error handling', () => {
    it('throws ApiError with correct status and detail', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Not found', code: 'not_found' }),
      } as Response)

      await expect(apiFetch('/test')).rejects.toThrow(ApiError)

      try {
        await apiFetch('/test')
      } catch (e) {
        expect(e).toBeInstanceOf(ApiError)
        if (e instanceof ApiError) {
          expect(e.status).toBe(404)
          expect(e.code).toBe('not_found')
          expect(e.message).toBe('Not found')
        }
      }
    })

    it('handles non-JSON error responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Invalid JSON')
        },
      } as Response)

      await expect(apiFetch('/test')).rejects.toThrow(ApiError)
    })

    it('returns undefined for 204 No Content', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
      } as Response)

      const result = await apiFetch('/test')
      expect(result).toBeUndefined()
    })
  })
})

describe('apiFetchBlob', () => {
  beforeEach(() => {
    useAuthStore.getState().logout()
    mockFetch.mockClear()
    mockLocation.href = ''
  })

  it('returns blob data', async () => {
    useAuthStore.getState().setAuth(
      { id: '1', github_id: 1, github_login: 'test', repo_created: false },
      'test-token',
      'refresh-token'
    )

    const mockBlob = new Blob(['test content'], { type: 'application/pdf' })
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: async () => mockBlob,
    } as Response)

    const result = await apiFetchBlob('/test.pdf')
    expect(result).toBe(mockBlob)
  })

  it('handles 401 with token refresh', async () => {
    useAuthStore.getState().setAuth(
      { id: '1', github_id: 1, github_login: 'test', repo_created: false },
      'expired-token',
      'valid-refresh-token'
    )

    const mockBlob = new Blob(['content'])
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'new-token' }),
        status: 200,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: async () => mockBlob,
      } as Response)

    const result = await apiFetchBlob('/test.pdf')
    expect(result).toBe(mockBlob)
  })
})

describe('api convenience methods', () => {
  beforeEach(() => {
    useAuthStore.getState().logout()
    mockFetch.mockClear()
  })

  it('api.get sends GET request', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: 'test' }),
      status: 200,
    } as Response)

    await api.get('/test')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: 'GET',
      })
    )
  })

  it('api.post sends POST request with JSON body', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
      status: 200,
    } as Response)

    await api.post('/test', { name: 'test' })

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'test' }),
      })
    )
  })

  it('api.upload sends FormData without Content-Type', async () => {
    useAuthStore.getState().setAuth(
      { id: '1', github_id: 1, github_login: 'test', repo_created: false },
      'test-token',
      'refresh-token'
    )

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
      status: 200,
    } as Response)

    const formData = new FormData()
    formData.append('file', new Blob(['content']))

    await api.upload('/test', formData)

    const callArgs = mockFetch.mock.calls[0]
    expect(callArgs[1]).toMatchObject({
      method: 'POST',
      body: formData,
    })
    // Verify Content-Type is not set by default for FormData
    expect(callArgs[1].headers).not.toHaveProperty('Content-Type')
  })

  it('api.delete sends DELETE request', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
      status: 200,
    } as Response)

    await api.delete('/test')

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: 'DELETE',
      })
    )
  })
})
