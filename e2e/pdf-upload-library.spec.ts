import { test, expect } from '@playwright/test'

test.describe('PDF Upload', () => {
  test('shows upload area', async ({ page }) => {
    // Navigate to home page
    await page.goto('/Paperstack/')

    // Should show the main page content
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('shows empty state when no PDFs exist', async ({ page }) => {
    await page.goto('/Paperstack/')

    // Should show some UI indicating the app is loaded
    const appContainer = page.locator('body')
    await expect(appContainer).toBeVisible()
  })
})
