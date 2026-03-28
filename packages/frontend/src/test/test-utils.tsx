/**
 * Test utilities for React component testing.
 */

import { render as originalRender, RenderOptions } from '@testing-library/react'
import { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'

// =============================================================================
// Custom Render Function
// =============================================================================

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient
  router?: boolean
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

/**
 * Custom render function that includes providers.
 *
 * @param ui - React element to render
 * @param options - Additional render options
 * @returns Render result with query client
 */
function renderWithProviders(
  ui: ReactElement,
  {
    queryClient = createTestQueryClient(),
    router = false,
    ...renderOptions
  }: CustomRenderOptions = {}
) {
  function Wrapper({ children }: { children: React.ReactNode }) {
    let content = <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>

    if (router) {
      content = <BrowserRouter>{content}</BrowserRouter>
    }

    return content
  }

  return {
    ...originalRender(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  }
}

// =============================================================================
// Zustand Store Testing Helpers
// =============================================================================

/**
 * Reset a Zustand store to its initial state.
 *
 * @param store - The Zustand store to reset
 */
export function resetStore<T extends { getState: () => unknown; setState: (state: Partial<T>) => void }>(
  store: T
) {
  store.setState({} as Partial<T>)
}

// =============================================================================
// Mock Data Generators
// =============================================================================

export function createMockPdf(overrides = {}) {
  return {
    id: 'pdf-1',
    user_id: 'user-1',
    title: 'Test PDF',
    filename: 'test.pdf',
    file_size: 12345,
    page_count: 10,
    uploaded_at: '2026-03-09T00:00:00Z',
    updated_at: '2026-03-09T00:00:00Z',
    doi: null,
    isbn: null,
    ...overrides,
  }
}

export function createMockAnnotation(overrides: Partial<import('@/api/annotations').Annotation> = {}) {
  const annotation: import('@/api/annotations').Annotation = {
    id: 'ann-1',
    set_id: 'set-1',
    page_number: 1,
    type: 'highlight',
    rects: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }],
    selected_text: null,
    note_content: null,
    color: '#FFFF00',
    created_at: '2026-03-09T00:00:00Z',
    updated_at: '2026-03-09T00:00:00Z',
  }
  return { ...annotation, ...overrides }
}

export function createMockAnnotationSet(overrides = {}) {
  return {
    id: 'set-1',
    pdf_id: 'pdf-1',
    name: 'Default',
    color: '#FFFF00',
    created_at: '2026-03-09T00:00:00Z',
    annotations: [],
    ...overrides,
  }
}

export function createMockCitation(overrides = {}) {
  return {
    id: 'cit-1',
    pdf_id: 'pdf-1',
    bibtex: '@article{test2024}',
    doi: '10.1234/test',
    title: 'Test Paper',
    authors: 'Test Author',
    year: 2024,
    source: 'manual',
    ...overrides,
  }
}

export function createMockUser(overrides = {}) {
  return {
    id: 'user-1',
    github_id: 123456,
    github_login: 'testuser',
    display_name: 'Test User',
    avatar_url: 'https://example.com/avatar.png',
    ...overrides,
  }
}

export function createMockCollection(overrides = {}) {
  return {
    id: 'col-1',
    name: 'Research',
    parent_id: null,
    position: 0,
    pdf_count: 0,
    ...overrides,
  }
}

export function createMockTag(overrides = {}) {
  return {
    id: 'tag-1',
    name: 'Important',
    color: '#FF0000',
    pdf_count: 0,
    ...overrides,
  }
}

// =============================================================================
// Re-exports
// =============================================================================

/**
 * Re-export everything from testing-library.
 */
export * from '@testing-library/react'

/**
 * Override render with our custom implementation that includes providers.
 * This must come after the wildcard export to override it.
 */
export { renderWithProviders as render }
