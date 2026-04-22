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
// Mock Data Generators
// =============================================================================

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
