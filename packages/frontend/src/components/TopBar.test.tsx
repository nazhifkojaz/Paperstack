import { render, screen } from '@/test/test-utils'
import { TopBar } from './TopBar'
import { beforeEach, describe, expect, test, vi } from 'vitest'

/**
 * Search bar tests moved to FilterBar.test.tsx since the search
 * input now lives in the library's FilterBar, not the global TopBar.
 */

describe('TopBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('renders Paperstack branding as a link to home', () => {
    render(<TopBar />, { router: true })

    const link = screen.getByRole('link', { name: /paperstack/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/')
  })
})
