import { test } from './fixtures/auth'
import { expect } from '@playwright/test'

test.describe('Login Flow', () => {
  test('shows login page when not authenticated', async ({ page }) => {
    await page.goto('/Paperstack/login')

    // Should show heading and login button
    await expect(page.getByRole('heading', { name: /Paperstack/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Continue with GitHub/i })).toBeVisible()
  })

  test('shows sign in message', async ({ page }) => {
    await page.goto('/Paperstack/login')

    // Should show sign in heading and description
    await expect(page.getByRole('heading', { name: /Sign in to continue/i })).toBeVisible()
    await expect(page.getByText(/uses GitHub to store your PDF files privately/i)).toBeVisible()
  })
})
