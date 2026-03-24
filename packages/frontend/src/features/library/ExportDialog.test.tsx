/**
 * Tests for ExportDialog component.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { ExportDialog } from './ExportDialog'

const mockMissingPdfs = [
  {
    id: 'pdf-1',
    title: 'Paper Without Citation',
    filename: 'no-citation.pdf',
    user_id: 'user-1',
    uploaded_at: '2026-03-01T10:00:00Z',
    updated_at: '2026-03-01T10:00:00Z',
  },
  {
    id: 'pdf-2',
    title: 'Another Missing',
    filename: 'another.pdf',
    user_id: 'user-1',
    uploaded_at: '2026-03-01T10:00:00Z',
    updated_at: '2026-03-01T10:00:00Z',
  },
]

describe('ExportDialog', () => {
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ExportDialog
        isOpen={false}
        hasCitationCount={5}
        missingPdfs={[]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(container.firstChild).toBeNull()
  })

  it('renders dialog when isOpen is true', () => {
    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={5}
        missingPdfs={[]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByText('Export Citations')).toBeTruthy()
  })

  it('shows success message when all PDFs have citations', () => {
    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={5}
        missingPdfs={[]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByText('All selected PDFs have citations ready for export.')).toBeTruthy()
    expect(screen.getByText('5 PDFs have citations')).toBeTruthy()
  })

  it('shows missing citations warning when some PDFs are missing citations', () => {
    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={3}
        missingPdfs={mockMissingPdfs}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByText('Some PDFs are missing citations.')).toBeTruthy()
    expect(screen.getByText('2 PDFs are missing citations:')).toBeTruthy()
    // PDF titles are in list items with bullets, use a more flexible matcher
    expect(screen.getByText((content) => content.includes('Paper Without Citation'))).toBeTruthy()
    expect(screen.getByText((content) => content.includes('Another Missing'))).toBeTruthy()
  })

  it('shows singular "is" when only one PDF is missing citations', () => {
    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={3}
        missingPdfs={[mockMissingPdfs[0]]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByText('1 PDF is missing citations:')).toBeTruthy()
  })

  it('shows warning message when there are missing PDFs', () => {
    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={3}
        missingPdfs={mockMissingPdfs}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByText('Only PDFs with citations will be included in the export.')).toBeTruthy()
  })

  it('calls onConfirm when Export button is clicked', () => {
    const handleConfirm = vi.fn()

    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={5}
        missingPdfs={[]}
        onConfirm={handleConfirm}
        onCancel={vi.fn()}
      />
    )

    const exportButton = screen.getByText('Export 5')
    fireEvent.click(exportButton)

    expect(handleConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when Cancel button is clicked', () => {
    const handleCancel = vi.fn()

    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={5}
        missingPdfs={[]}
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    )

    const cancelButton = screen.getByText('Cancel')
    fireEvent.click(cancelButton)

    expect(handleCancel).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when close button is clicked', () => {
    const handleCancel = vi.fn()

    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={5}
        missingPdfs={[]}
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    )

    // Find and click the close (X) button
    const closeButton = screen.getByRole('button', { name: /close/i })
    fireEvent.click(closeButton)

    expect(handleCancel).toHaveBeenCalledTimes(1)
  })

  it('displays PDF filename when title is missing', () => {
    const pdfWithoutTitle = {
      id: 'pdf-3',
      title: '',
      filename: 'untitled-paper.pdf',
      user_id: 'user-1',
      uploaded_at: '2026-03-01T10:00:00Z',
      updated_at: '2026-03-01T10:00:00Z',
    }

    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={0}
        missingPdfs={[pdfWithoutTitle]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    // Filename is inside list item with bullet, use more flexible matcher
    expect(screen.getByText((content) => content.includes('untitled-paper.pdf'))).toBeTruthy()
  })

  it('does not show citations count when hasCitationCount is 0', () => {
    render(
      <ExportDialog
        isOpen={true}
        hasCitationCount={0}
        missingPdfs={mockMissingPdfs}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.queryByText(/PDFs have citations/)).toBeNull()
  })
})
