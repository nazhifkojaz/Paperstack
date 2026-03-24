import { test as base, type Page } from '@playwright/test'

/**
 * Injects a fake auth token into localStorage so ProtectedLayout passes,
 * and intercepts all API calls to return empty 200 responses. This prevents
 * the API client from triggering logout (on 401) which would redirect to /login.
 *
 * Call this before page.goto(). addInitScript runs before any page script.
 */
export async function mockAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('paperstack-auth', JSON.stringify({
      state: {
        user: {
          id: 'test-user',
          github_id: 12345,
          github_login: 'testuser',
          display_name: 'Test User',
          avatar_url: '',
          repo_created: true,
        },
        accessToken: 'fake-access-token-for-e2e-testing',
        refreshToken: 'fake-refresh-token-for-e2e-testing',
      },
      version: 0,
    }))
  })

  // Intercept API calls so the fake token never triggers a 401-based logout
  await page.route('**/v1/**', async (route) => {
    const method = route.request().method()
    const url = route.request().url()

    // List endpoints → empty array
    const isListEndpoint = /\/(pdfs|collections|tags|shares|annotation-sets|annotations|auto-highlight)(\?.*)?$/.test(url)

    if (method === 'GET') {
      if (isListEndpoint) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      } else {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Not found', code: 'not_found' }) })
      }
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    }
  })
}

export const test = base.extend<{
  authenticatedPage: typeof test.extend extends (...args: any[]) => infer R ? R : never
}>({
  authenticatedPage: async ({ page }, use) => {
    // For E2E tests, we'll need to mock or use a test GitHub OAuth flow
    // For now, we'll skip actual auth and focus on testing without it
    await page.goto('/Paperstack/')
    await use(page)
  },
})
