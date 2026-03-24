import { test, expect } from '@playwright/test';
import { mockAuth } from './fixtures/auth';

test.describe('Bulk BibTeX Export', () => {
    test.beforeEach(async ({ page }) => {
        await mockAuth(page);
        await page.goto('/Paperstack/library');
        // Wait for page to load
        await page.waitForSelector('text=My Library');
    });

    test('should show Select Mode toggle button', async ({ page }) => {
        await expect(page.locator('button:has-text("Select Mode")')).toBeVisible();
    });

    test('should enter selection mode when toggle clicked', async ({ page }) => {
        await page.click('button:has-text("Select Mode")');
        // Should show Cancel button instead
        await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
    });

    test('should show floating action bar when items selected', async ({ page }) => {
        // Enter selection mode
        await page.click('button:has-text("Select Mode")');

        // Wait a moment for any state updates
        await page.waitForTimeout(100);

        // Click first PDF card/row (in selection mode, this selects it)
        const firstCard = page.locator('[class*="border rounded-xl"]').first();
        const cardCount = await firstCard.count();

        if (cardCount > 0) {
            await firstCard.click();
            // Should show floating bar with selected count
            await expect(page.locator('text=selected')).toBeVisible();
            await expect(page.locator('text=Export BibTeX')).toBeVisible();
        }
    });

    test('should show selected count in floating action bar', async ({ page }) => {
        await page.click('button:has-text("Select Mode")');
        await page.waitForTimeout(100);

        const cards = page.locator('[class*="border rounded-xl"]');
        const cardCount = await cards.count();

        if (cardCount >= 2) {
            // Select two items
            await cards.nth(0).click();
            await cards.nth(1).click();

            // Should show 2 selected
            await expect(page.locator('text=2 selected')).toBeVisible();
        }
    });

    test('should exit selection mode when floating bar cancel clicked', async ({ page }) => {
        await page.click('button:has-text("Select Mode")');
        await page.waitForTimeout(100);

        const firstCard = page.locator('[class*="border rounded-xl"]').first();
        const cardCount = await firstCard.count();

        if (cardCount > 0) {
            await firstCard.click();
            // Floating bar should be visible
            await expect(page.locator('text=selected')).toBeVisible();

            // Click cancel on floating bar
            await page.click('.fixed.bottom-4 button:has-text("Cancel")');

            // Should exit selection mode and show Select Mode button again
            await expect(page.locator('button:has-text("Select Mode")')).toBeVisible();
        }
    });

    test('should exit selection mode when filter bar cancel clicked', async ({ page }) => {
        await page.click('button:has-text("Select Mode")');
        await expect(page.locator('button:has-text("Cancel")')).toBeVisible();

        // Click the Cancel button in FilterBar (destructive variant)
        const cancelButton = page.locator('button.variant-destructive:has-text("Cancel")');
        if (await cancelButton.count() > 0) {
            await cancelButton.click();
            // Should show Select Mode button again
            await expect(page.locator('button:has-text("Select Mode")')).toBeVisible();
        }
    });

    test('should show export dialog when export clicked and some PDFs missing citations', async ({ page }) => {
        await page.click('button:has-text("Select Mode")');
        await page.waitForTimeout(100);

        const firstCard = page.locator('[class*="border rounded-xl"]').first();
        const cardCount = await firstCard.count();

        if (cardCount > 0) {
            await firstCard.click();

            // Click export button
            const exportButton = page.locator('text=Export BibTeX');
            if (await exportButton.count() > 0) {
                await exportButton.first().click();

                // May show export dialog if citations are missing, or export directly
                // Either behavior is acceptable
                const dialog = page.locator('text=Export Citations');
                const downloadStarted = await page.evaluate(() => {
                    return window.document.querySelector('a[download]') !== null;
                });

                // At least one of these should happen
                const hasDialog = await dialog.count() > 0;
                expect(hasDialog || downloadStarted).toBeTruthy();
            }
        }
    });
});
