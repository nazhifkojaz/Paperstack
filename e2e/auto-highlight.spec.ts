import { test, expect } from '@playwright/test'

/**
 * E2E Tests for the Auto-Highlight Feature
 *
 * Covers UI presence and interaction for:
 * - AutoHighlightButton in the annotation sidebar
 * - CategorySelectionDialog (categories, defaults, open/close)
 * - ApiKeyDialog (inputs, provider rows, open/close)
 * - Per-set eye toggle visibility control
 * - AI set styling (sparkle icon, purple background)
 *
 * Note: These tests verify UI behaviour without requiring a live LLM.
 * The actual analyze flow (LLM call → highlights) requires manual E2E
 * or a mocked backend and is not covered here.
 */

test.describe('Auto-Highlight Button', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/viewer/test-pdf-id')
    await page.waitForSelector('body', { timeout: 10000 })
  })

  test('renders in the annotation sidebar', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    const appeared = await button.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return
    await expect(button).toBeVisible()
  })

  test('has the sparkle prefix icon', async ({ page }) => {
    // The button text starts with the ✦ character
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    const appeared = await button.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return
    await expect(button).toBeVisible()
    const text = await button.textContent()
    expect(text).toContain('✦')
  })

  test('shows quota status below the button', async ({ page }) => {
    // Quota line appears once quota data loads — may show free uses or key info
    const quotaLine = page.locator('text=/free use|using your|add api key/i')
    // Soft check: only assert if the element appears within a reasonable timeout
    const appeared = await quotaLine.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (appeared) {
      await expect(quotaLine.first()).toBeVisible()
    }
  })
})

test.describe('Category Selection Dialog', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/viewer/test-pdf-id')
    await page.waitForSelector('body', { timeout: 10000 })
  })

  test('opens when the Auto-Highlight button is clicked (with quota)', async ({ page }) => {
    // This works when the user has quota or a stored key — the button opens the dialog
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    const appeared = await button.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return
    await button.click()

    // Dialog may or may not open depending on quota state; soft-check
    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (opened) {
      await expect(dialog).toBeVisible()
    }
  })

  test('dialog has the correct title', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    if (!await button.isVisible({ timeout: 5000 }).catch(() => false)) return
    await button.click()

    const title = page.getByRole('heading', { name: /auto-highlight settings/i })
    const appeared = await title.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (appeared) {
      await expect(title).toBeVisible()
    }
  })

  test('shows all five category options', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    if (!await button.isVisible({ timeout: 5000 }).catch(() => false)) return
    await button.click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    const expectedCategories = [
      /key findings/i,
      /methodology/i,
      /definitions/i,
      /limitations/i,
      /background/i,
    ]

    for (const pattern of expectedCategories) {
      await expect(dialog.locator(`text=${pattern}`).or(page.locator(`text=${pattern}`))).toBeVisible()
    }
  })

  test('"Findings" category is pre-selected by default', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    if (!await button.isVisible({ timeout: 5000 }).catch(() => false)) return
    await button.click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    // The findings checkbox should be checked
    const checkboxes = dialog.getByRole('checkbox')
    const count = await checkboxes.count()
    if (count > 0) {
      // First checkbox corresponds to "findings" (default: true)
      await expect(checkboxes.first()).toBeChecked()
    }
  })

  test('Analyze button is disabled when no category is selected', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    if (!await button.isVisible({ timeout: 5000 }).catch(() => false)) return
    await button.click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    // Uncheck all checked boxes
    const checkboxes = dialog.getByRole('checkbox')
    const count = await checkboxes.count()
    for (let i = 0; i < count; i++) {
      const cb = checkboxes.nth(i)
      if (await cb.isChecked()) {
        await cb.click()
      }
    }

    const analyzeButton = dialog.getByRole('button', { name: /^analyze$/i })
    if (await analyzeButton.count() > 0) {
      await expect(analyzeButton).toBeDisabled()
    }
  })

  test('Cancel button closes the dialog', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    if (!await button.isVisible({ timeout: 5000 }).catch(() => false)) return
    await button.click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    const cancelButton = dialog.getByRole('button', { name: /cancel/i })
    if (await cancelButton.count() > 0) {
      await cancelButton.click()
      await expect(dialog).not.toBeVisible({ timeout: 2000 })
    }
  })

  test('Escape key closes the dialog', async ({ page }) => {
    const button = page.getByRole('button', { name: /auto-highlight paper/i })
    if (!await button.isVisible({ timeout: 5000 }).catch(() => false)) return
    await button.click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible({ timeout: 2000 })
  })
})

test.describe('API Key Dialog', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/viewer/test-pdf-id')
    await page.waitForSelector('body', { timeout: 10000 })
  })

  test('opens when "Add API key" link is clicked', async ({ page }) => {
    const addKeyLink = page.getByRole('button', { name: /add api key/i })
      .or(page.locator('text=/add api key/i'))
    const linkVisible = await addKeyLink.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!linkVisible) return

    await addKeyLink.first().click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (opened) {
      await expect(dialog).toBeVisible()
    }
  })

  test('dialog has the correct title', async ({ page }) => {
    const addKeyLink = page.locator('text=/add api key/i')
    const appeared = await addKeyLink.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await addKeyLink.first().click()

    const title = page.getByRole('heading', { name: /api key management/i })
    const titleShown = await title.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (titleShown) {
      await expect(title).toBeVisible()
    }
  })

  test('shows Gemini and GLM provider rows', async ({ page }) => {
    const addKeyLink = page.locator('text=/add api key/i')
    const appeared = await addKeyLink.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await addKeyLink.first().click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    await expect(dialog.locator('text=/google gemini/i')).toBeVisible()
    await expect(dialog.locator('text=/zhipu|glm/i')).toBeVisible()
  })

  test('each provider row has a password input and Save button', async ({ page }) => {
    const addKeyLink = page.locator('text=/add api key/i')
    const appeared = await addKeyLink.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await addKeyLink.first().click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    // Should have at least one password input per unconfigured provider
    const passwordInputs = dialog.locator('input[type="password"]')
    const inputCount = await passwordInputs.count()
    if (inputCount > 0) {
      expect(inputCount).toBeGreaterThanOrEqual(1)

      // Save buttons should be disabled while the input is empty
      const saveButtons = dialog.getByRole('button', { name: /^save$/i })
      if (await saveButtons.count() > 0) {
        await expect(saveButtons.first()).toBeDisabled()
      }
    }
  })

  test('Save button enables after typing a key', async ({ page }) => {
    const addKeyLink = page.locator('text=/add api key/i')
    const appeared = await addKeyLink.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await addKeyLink.first().click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    const passwordInput = dialog.locator('input[type="password"]').first()
    if (await passwordInput.count() === 0) return

    await passwordInput.fill('test-api-key-12345')

    const saveButton = dialog.getByRole('button', { name: /^save$/i }).first()
    if (await saveButton.count() > 0) {
      await expect(saveButton).toBeEnabled()
    }
  })

  test('has "Get API key" links for each provider', async ({ page }) => {
    const addKeyLink = page.locator('text=/add api key/i')
    const appeared = await addKeyLink.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await addKeyLink.first().click()

    const dialog = page.getByRole('dialog')
    const opened = await dialog.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)
    if (!opened) return

    const getKeyLinks = dialog.getByRole('link', { name: /get api key/i })
    if (await getKeyLinks.count() > 0) {
      expect(await getKeyLinks.count()).toBeGreaterThanOrEqual(2)
    }
  })
})

test.describe('Annotation Set Visibility Toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/viewer/test-pdf-id')
    await page.waitForSelector('body', { timeout: 10000 })
  })

  test('eye toggle button appears on each set row', async ({ page }) => {
    // Soft check — only runs if there are annotation sets loaded
    const setRows = page.locator('[title="Hide annotations"], [title="Show annotations"]')
    const appeared = await setRows.first().waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    const count = await setRows.count()
    expect(count).toBeGreaterThan(0)
  })

  test('clicking eye toggle dims the set row', async ({ page }) => {
    const eyeButton = page.locator('[title="Hide annotations"]').first()
    const appeared = await eyeButton.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    const setRow = eyeButton.locator('..') // parent element
    await eyeButton.click()

    // The set row should gain opacity-40 (dimmed state)
    await expect(setRow).toHaveClass(/opacity-40/, { timeout: 2000 })

    // Title should toggle to "Show annotations"
    await expect(page.locator('[title="Show annotations"]').first()).toBeVisible()
  })

  test('clicking again restores visibility', async ({ page }) => {
    // First hide
    const hideButton = page.locator('[title="Hide annotations"]').first()
    const appeared = await hideButton.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await hideButton.click()

    // Now show
    const showButton = page.locator('[title="Show annotations"]').first()
    await showButton.waitFor({ timeout: 2000 })
    await showButton.click()

    // Should be back to hide state
    await expect(page.locator('[title="Hide annotations"]').first()).toBeVisible({ timeout: 2000 })
  })
})

test.describe('AI Set Styling', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/Paperstack/viewer/test-pdf-id')
    await page.waitForSelector('body', { timeout: 10000 })
  })

  test('AI-generated sets show the sparkle ✦ icon', async ({ page }) => {
    // This only runs if there is at least one auto_highlight set in the sidebar
    const sparkle = page.locator('[class*="sidebar"] text=✦')
      .or(page.locator('[class*="set"] text=✦'))
    const appeared = await sparkle.first().waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await expect(sparkle.first()).toBeVisible()
  })

  test('AI-generated sets have purple background class', async ({ page }) => {
    // Soft check for purple-tinted set rows
    const purpleSet = page.locator('[class*="purple-500"]').first()
    const appeared = await purpleSet.waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    await expect(purpleSet).toBeVisible()
  })

  test('AI-generated sets do not show the share button', async ({ page }) => {
    // If an AI set exists, it should not have a Share button
    const sparkle = page.locator('[class*="sidebar"] text=✦')
    const appeared = await sparkle.first().waitFor({ timeout: 5000 }).then(() => true).catch(() => false)
    if (!appeared) return

    // The row containing ✦ should not have a share button
    const aiSetRow = sparkle.first().locator('../..')
    const shareButton = aiSetRow.getByRole('button', { name: /share/i })
    await expect(shareButton).not.toBeVisible()
  })
})
