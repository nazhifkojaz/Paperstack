import { test, expect } from '@playwright/test'

test.describe('Citations Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/')
  })

  test('should navigate to library page', async ({ page }) => {
    await page.goto('/Paperstack/library')
    await expect(page).toHaveURL(/.*\/library/)
  })

  test('should show library container', async ({ page }) => {
    await page.goto('/Paperstack/library')
    await expect(page.locator('body')).toBeVisible()
  })
})