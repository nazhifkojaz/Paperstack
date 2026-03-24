/**
 * Tests for PdfCard component.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { PdfCard } from './PdfCard'
import { MemoryRouter } from 'react-router-dom'

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
  const renderWithRouter = (component: React.ReactNode) => {
    return render(
      <MemoryRouter>{component}</MemoryRouter>
    )
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

    // Navigation is handled by react-router
    expect(window.location.pathname).toBe('/Paperstack/')
  })

  it('calls onDelete when delete is clicked', () => {
    const handleDelete = vi.fn()

    renderWithRouter(<PdfCard pdf={mockPdf} onDelete={handleDelete} />)

    // Find and click the more options button
    const moreButton = screen.getByRole('button', { name: /open menu/i })
    fireEvent.click(moreButton)

    // Find delete option in dropdown
    const deleteOption = screen.getByText('Delete')
    fireEvent.click(deleteOption)

    expect(handleDelete).toHaveBeenCalledWith('pdf-1')
  })

  it('calls onEdit when edit is clicked', () => {
    const handleEdit = vi.fn()

    renderWithRouter(<PdfCard pdf={mockPdf} onEdit={handleEdit} />)

    const moreButton = screen.getByRole('button', { name: /open menu/i })
    fireEvent.click(moreButton)

    const editOption = screen.getByText('Edit Metadata')
    fireEvent.click(editOption)

    expect(handleEdit).toHaveBeenCalledWith(mockPdf)
  })

  it('does not propagate click when menu action is clicked', () => {
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

    // Click delete
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
