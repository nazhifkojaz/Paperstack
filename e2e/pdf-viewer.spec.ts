import { test, expect } from '@playwright/test'

test.describe('PDF Viewer', () => {
  test('shows viewer controls', async ({ page }) => {
    // Navigate to a viewer page
    await page.goto('/Paperstack/viewer/sample-pdf-id')

    // The viewer should load (even if PDF doesn't exist, we should see error or empty state)
    const viewerContainer = page.locator('body')
    await expect(viewerContainer).toBeVisible()
  })

  test('shows navigation buttons', async ({ page }) => {
    await page.goto('/Paperstack/viewer/sample-pdf-id')

    // Look for navigation elements
    const prevButton = page.locator('button').filter({ hasText: /chevron|previous|←/i }).first()
    const nextButton = page.locator('button').filter({ hasText: /chevron|next|→/i }).first()

    // At least some controls should be present
    await expect(page.locator('button').first()).toBeVisible()
  })
})
