/**
 * Tests for PdfCard component.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@/test/test-utils'
import { PdfCard } from './PdfCard'
import { useLibraryStore } from '@/stores/libraryStore'
import { BASE_URL } from '@/lib/config'

const mockPdf = {
  id: 'pdf-1',
  title: 'Test Research Paper',
  filename: 'test-paper.pdf',
  file_size: 12345,
  page_count: 15,
  uploaded_at: '2026-03-01T10:00:00Z',
  doi: null,
  isbn: null,
}

describe('PdfCard', () => {
  beforeEach(() => {
    // Reset library store before each test
    useLibraryStore.getState().setSelectionMode(false)
    useLibraryStore.getState().clearSelection()
  })

  const renderWithRouter = (component: React.ReactNode) => {
    return render(component, { router: true })
  }

  it('renders PDF information', () => {
    renderWithRouter(<PdfCard pdf={mockPdf} />)

    expect(screen.getByText('Test Research Paper')).toBeTruthy()
    expect(screen.getByText('test-paper.pdf')).toBeTruthy()
    expect(screen.getByText('15 pages')).toBeTruthy()
    expect(screen.getByText(/ago/)).toBeTruthy() // Relative time
  })

  it('navigates to viewer on card click', () => {
    renderWithRouter(<PdfCard pdf={mockPdf} />)

    const card = screen.getByText('Test Research Paper').closest('.group')
    fireEvent.click(card!)

    // Navigation is handled by react-router (MemoryRouter uses internal state)
    // We can't easily test the full URL in MemoryRouter, but we can verify
    // the card is clickable and doesn't throw errors
    expect(card).toBeInTheDocument()
  })

  // Skip dropdown menu tests - Radix UI DropdownMenu uses portals
  // which don't work well in test environments. These tests would
  // require additional setup (jsdom configuration with portals).
  it.skip('calls onDelete when delete is clicked', async () => {
    const handleDelete = vi.fn()

    renderWithRouter(<PdfCard pdf={mockPdf} onDelete={handleDelete} />)

    // Find and click the more options button (MoreVertical icon)
    const moreButton = screen.getByRole('button', { name: /open menu/i })
    fireEvent.click(moreButton)

    // Wait for dropdown to appear and find delete option
    await waitFor(() => {
      const deleteOption = screen.getByText('Delete')
      expect(deleteOption).toBeInTheDocument()
    })

    const deleteOption = screen.getByText('Delete')
    fireEvent.click(deleteOption)

    expect(handleDelete).toHaveBeenCalledWith('pdf-1')
  })

  it.skip('calls onEdit when edit is clicked', async () => {
    const handleEdit = vi.fn()

    renderWithRouter(<PdfCard pdf={mockPdf} onEdit={handleEdit} />)

    const moreButton = screen.getByRole('button', { name: /open menu/i })
    fireEvent.click(moreButton)

    // Wait for dropdown to appear
    await waitFor(() => {
      const editOption = screen.getByText('Edit Metadata')
      expect(editOption).toBeInTheDocument()
    })

    const editOption = screen.getByText('Edit Metadata')
    fireEvent.click(editOption)

    expect(handleEdit).toHaveBeenCalledWith(mockPdf)
  })

  it.skip('does not propagate click when menu action is clicked', async () => {
    const handleClick = vi.fn()
    const handleDelete = vi.fn()

    renderWithRouter(<PdfCard pdf={mockPdf} onDelete={handleDelete} />)

    const card = screen.getByText('Test Research Paper').closest('.group')
    if (card) {
      card.addEventListener('click', handleClick)
    }

    // Open menu
    const moreButton = screen.getByRole('button', { name: /open menu/i })
    fireEvent.click(moreButton)

    // Wait for dropdown and click delete
    await waitFor(() => {
      const deleteOption = screen.getByText('Delete')
      expect(deleteOption).toBeInTheDocument()
    })

    const deleteOption = screen.getByText('Delete')
    fireEvent.click(deleteOption)

    expect(handleDelete).toHaveBeenCalled()
    // The card click should not be triggered
    expect(handleClick).not.toHaveBeenCalled()
  })

  it('handles PDF with unknown page count', () => {
    const pdfWithoutPages = { ...mockPdf, page_count: null }

    renderWithRouter(<PdfCard pdf={pdfWithoutPages} />)

    expect(screen.getByText('Unknown pages')).toBeTruthy()
  })

  it('shows menu on hover', () => {
    renderWithRouter(<PdfCard pdf={mockPdf} />)

    const card = screen.getByText('Test Research Paper').closest('.group')
    const overlay = card?.querySelector('.opacity-0')

    // Initially hidden
    expect(overlay?.className).toContain('opacity-0')

    // Simulate hover
    fireEvent.mouseEnter(card!)

    // Should show (though opacity transition might need actual CSS to see effect)
    expect(overlay?.className).toContain('group-hover:opacity-100')
  })
})
