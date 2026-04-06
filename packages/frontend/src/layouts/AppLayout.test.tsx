import { render, screen } from '@/test/test-utils'
import { AppLayout } from './AppLayout'
import { beforeEach, describe, expect, test, vi } from 'vitest'

/**
 * Sidebar-related tests have been removed since the sidebar is
 * temporarily hidden. See Sidebar.test.tsx for sidebar-specific tests
 * (kept for when the sidebar is re-enabled).
 */

describe('AppLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('renders main content area', () => {
    render(<AppLayout />, { router: true })

    const main = screen.getByRole('main')
    expect(main).toBeInTheDocument()
  })

  test('renders top bar', () => {
    render(<AppLayout />, { router: true })

    const header = screen.getByRole('banner')
    expect(header).toBeInTheDocument()
  })
})
