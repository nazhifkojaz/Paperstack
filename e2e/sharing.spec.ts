import { test, expect } from '@playwright/test'

test.describe('Sharing Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/')
  })

  test('should navigate to shared page route', async ({ page }) => {
    await page.goto('/Paperstack/shared/test-token')
    await expect(page).toHaveURL(/.*\/shared\/.*/)
  })

  test('should show shared page container', async ({ page }) => {
    await page.goto('/Paperstack/shared/test-token')
    await expect(page.locator('body')).toBeVisible()
  })
})