import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
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
    render(
      <BrowserRouter>
        <TopBar />
      </BrowserRouter>
    )

    const link = screen.getByRole('link', { name: /paperstack/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/')
  })
})
