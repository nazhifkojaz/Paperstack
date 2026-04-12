import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@/test/test-utils'
import { ChatMessageList, type ChatMessageProps } from './ChatMessageList'

function createMockMessage(overrides: Partial<ChatMessageProps> = {}): ChatMessageProps {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: 'Hello world',
    context_chunks: null,
    ...overrides,
  }
}

const multiPageChunk = {
  chunk_id: 'c1',
  page_number: 5,
  end_page_number: 6,
  snippet: 'test snippet',
}

const singlePageChunk = {
  chunk_id: 'c2',
  page_number: 3,
  snippet: 'test snippet',
}

describe('ChatMessageList', () => {
  describe('context chunk badges', () => {
    it('shows p.5-6 for a multi-page chunk', () => {
      render(
        <ChatMessageList
          messages={[createMockMessage({ context_chunks: [multiPageChunk] })]}
        />
      )

      expect(screen.getByText('p.5-6')).toBeInTheDocument()
    })

    it('shows p.3 for a single-page chunk without end_page_number', () => {
      render(
        <ChatMessageList
          messages={[createMockMessage({ context_chunks: [singlePageChunk] })]}
        />
      )

      expect(screen.getByText('p.3')).toBeInTheDocument()
    })

    it('shows pdf title and page range for multi-page chunk with pdf info', () => {
      const chunk = {
        ...multiPageChunk,
        pdf_id: 'pdf-1',
        pdf_title: 'My Research Paper',
      }

      render(
        <ChatMessageList
          messages={[createMockMessage({ context_chunks: [chunk] })]}
        />
      )

      expect(screen.getByText(/My Research Paper · p\.5-6/)).toBeInTheDocument()
    })

    it('truncates long pdf titles in badge', () => {
      const chunk = {
        ...singlePageChunk,
        pdf_id: 'pdf-1',
        pdf_title: 'A Very Long Paper Title That Should Be Truncated',
      }

      render(
        <ChatMessageList
          messages={[createMockMessage({ context_chunks: [chunk] })]}
        />
      )

      expect(screen.getByText(/A Very Long Paper … · p\.3/)).toBeInTheDocument()
    })

    it('calls onChunkClick when badge is clicked', () => {
      const onChunkClick = vi.fn()

      render(
        <ChatMessageList
          messages={[createMockMessage({ context_chunks: [singlePageChunk] })]}
          onChunkClick={onChunkClick}
        />
      )

      fireEvent.click(screen.getByText('p.3'))
      expect(onChunkClick).toHaveBeenCalledWith(singlePageChunk)
    })

    it('shows p.3 when end_page_number equals page_number', () => {
      const chunk = {
        ...singlePageChunk,
        end_page_number: 3,
      }

      render(
        <ChatMessageList
          messages={[createMockMessage({ context_chunks: [chunk] })]}
        />
      )

      expect(screen.getByText('p.3')).toBeInTheDocument()
    })
  })

  describe('clickable page references in markdown', () => {
    it('renders [Page 5] as a clickable button when onPageClick is provided', () => {
      const onPageClick = vi.fn()

      render(
        <ChatMessageList
          messages={[createMockMessage({ content: 'See [Page 5] for details.' })]}
          onPageClick={onPageClick}
        />
      )

      const button = screen.getByRole('button', { name: /\[Page 5\]/ })
      expect(button).toBeInTheDocument()
      fireEvent.click(button)
      expect(onPageClick).toHaveBeenCalledWith(5)
    })

    it('renders [Pages 3-5] as a clickable button navigating to page 3', () => {
      const onPageClick = vi.fn()

      render(
        <ChatMessageList
          messages={[createMockMessage({ content: 'Discussed in [Pages 3-5].' })]}
          onPageClick={onPageClick}
        />
      )

      const button = screen.getByRole('button', { name: /\[Pages 3-5\]/ })
      fireEvent.click(button)
      expect(onPageClick).toHaveBeenCalledWith(3)
    })

    it('renders [Page 5] as plain text when onPageClick is not provided', () => {
      render(
        <ChatMessageList
          messages={[createMockMessage({ content: 'See [Page 5] for details.' })]}
        />
      )

      // No button should exist for the page ref
      expect(screen.queryByRole('button', { name: /\[Page 5\]/ })).not.toBeInTheDocument()
      // The text should still be visible
      expect(screen.getByText(/\[Page 5\]/)).toBeInTheDocument()
    })

    it('preserves regular markdown links as <a> tags', () => {
      const onPageClick = vi.fn()

      render(
        <ChatMessageList
          messages={[createMockMessage({ content: 'Visit [our site](https://example.com) for more.' })]}
          onPageClick={onPageClick}
        />
      )

      const link = screen.getByRole('link', { name: /our site/ })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', 'https://example.com')
    })
  })

  describe('empty state', () => {
    it('shows empty message when no messages', () => {
      render(
        <ChatMessageList
          messages={[]}
          emptyMessage="No messages yet."
        />
      )

      expect(screen.getByText('No messages yet.')).toBeInTheDocument()
    })
  })
})
