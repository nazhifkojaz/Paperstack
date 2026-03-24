import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { ErrorBoundary } from 'react-error-boundary'
import { Toaster } from 'sonner'
import { router } from '@/router'
import { ErrorBoundaryFallback } from '@/components/ErrorBoundary'
import './index.css'

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 60 * 1000, // 1 minute
            retry: 1,
        },
    },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ErrorBoundary FallbackComponent={ErrorBoundaryFallback}>
            <QueryClientProvider client={queryClient}>
                <RouterProvider router={router} />
                <Toaster richColors position="top-right" />
            </QueryClientProvider>
        </ErrorBoundary>
    </React.StrictMode>,
)

