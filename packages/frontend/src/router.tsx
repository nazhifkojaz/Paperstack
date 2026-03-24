import { createBrowserRouter, Navigate } from 'react-router-dom'
import { LoginPage } from '@/features/auth/LoginPage'
import { OAuthCallbackPage } from '@/features/auth/OAuthCallbackPage'
import { ProtectedLayout } from '@/layouts/ProtectedLayout'
import { AppLayout } from '@/layouts/AppLayout'

export const router = createBrowserRouter(
    [
        { path: '/login', element: <LoginPage /> },
        { path: '/auth/callback', element: <OAuthCallbackPage /> },
        {
            path: '/',
            element: <ProtectedLayout />,
            children: [
                {
                    element: <AppLayout />,
                    children: [
                        { index: true, element: <Navigate to="/library" replace /> },
                        {
                            path: 'library',
                            lazy: () =>
                                import('@/features/library/LibraryPage').then((m) => ({
                                    Component: m.LibraryPage,
                                })),
                        },
                        {
                            path: 'library/collection/:collectionId',
                            lazy: () =>
                                import('@/features/library/LibraryPage').then((m) => ({
                                    Component: m.LibraryPage,
                                })),
                        },
                        {
                            path: 'library/tag/:tagId',
                            lazy: () =>
                                import('@/features/library/LibraryPage').then((m) => ({
                                    Component: m.LibraryPage,
                                })),
                        },
                        {
                            path: 'chat/collection/:collectionId',
                            lazy: () =>
                                import('@/features/chat/CollectionChatPage').then((m) => ({
                                    Component: m.CollectionChatPage,
                                })),
                        },
                    ],
                },
                {
                    path: 'viewer/:pdfId',
                    lazy: () =>
                        import('@/features/viewer/ViewerPage').then((m) => ({
                            Component: m.ViewerPage,
                        })),
                },
            ],
        },
        {
            path: '/shared/:token',
            lazy: () =>
                import('@/features/sharing/SharedViewerPage').then((m) => ({
                    Component: m.SharedViewerPage,
                })),
        },
    ],
    { basename: '/Paperstack' },
)
