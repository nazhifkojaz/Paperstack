import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
    plugins: [
        react(),
        tailwindcss(),
        visualizer({
            open: process.env.CI !== 'true',
            filename: 'dist/stats.html',
            gzipSize: true,
            brotliSize: true,
        }),
    ],
    base: '/Paperstack/',
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: {
        port: 5173,
        proxy: {
            '/v1': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks: (id) => {
                    // PDF.js — heaviest dependency, only needed in viewer
                    if (id.includes('pdfjs-dist')) return 'pdf-vendor'

                    // Radix UI — UI foundation, updates together
                    if (id.includes('@radix-ui')) return 'ui-vendor'

                    // TanStack Query — data fetching, independent versioning
                    if (id.includes('@tanstack/react-query')) return 'query-vendor'

                    // React Router — routing, separate concern
                    // Match both react-router and react-router-dom packages
                    if (/\/react-router(-dom)?@/.test(id)) return 'router-vendor'

                    // Everything else (react, react-dom, zustand, etc.)
                    if (id.includes('node_modules')) return 'vendor'
                },
            },
        },
    },
})
