import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FloatingActionBar } from './FloatingActionBar'

describe('FloatingActionBar', () => {
  it('should not render when no items selected', () => {
    const { container } = render(
      <FloatingActionBar
        selectedCount={0}
        onExport={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(container.firstChild).toBeNull()
  })

  it('should render with correct count', () => {
    render(
      <FloatingActionBar
        selectedCount={5}
        onExport={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText('5 selected')).toBeInTheDocument()
  })

  it('should call onExport when export button clicked', () => {
    const onExport = vi.fn()
    render(
      <FloatingActionBar
        selectedCount={3}
        onExport={onExport}
        onCancel={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('Export BibTeX'))
    expect(onExport).toHaveBeenCalled()
  })

  it('should call onCancel when cancel button clicked', () => {
    const onCancel = vi.fn()
    render(
      <FloatingActionBar
        selectedCount={2}
        onExport={vi.fn()}
        onCancel={onCancel}
      />
    )
    fireEvent.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalled()
  })
})
