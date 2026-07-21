import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/test-utils'
import { CollectionTimeline } from './CollectionTimeline'

describe('CollectionTimeline', () => {
    it('shows empty state when no papers', () => {
        render(<CollectionTimeline papers={[]} />)
        expect(
            screen.getByText('No papers in this collection yet.'),
        ).toBeInTheDocument()
    })

    it('groups papers by year descending', () => {
        const papers = [
            { id: '1', title: 'Old Paper', year: 2020, first_author: 'Doe' },
            { id: '2', title: 'New Paper', year: 2024, first_author: 'Smith' },
            { id: '3', title: 'Mid Paper', year: 2022, first_author: null },
        ]
        render(<CollectionTimeline papers={papers} />, { router: true })

        const years = screen.getAllByText(/^(2020|2022|2024)$/)
        const yearTexts = years.map((y) => y.textContent)
        // Descending: 2024 first, then 2022, then 2020
        expect(yearTexts).toEqual(['2024', '2022', '2020'])
        expect(screen.getByText('New Paper')).toBeInTheDocument()
        expect(screen.getByText('Old Paper')).toBeInTheDocument()
        expect(screen.getByText('Mid Paper')).toBeInTheDocument()
    })

    it('collects papers without year into Unknown group at the bottom', () => {
        const papers = [
            { id: '1', title: 'Dated', year: 2023, first_author: null },
            { id: '2', title: 'Undated', year: null, first_author: null },
        ]
        render(<CollectionTimeline papers={papers} />, { router: true })

        expect(screen.getByText('Unknown')).toBeInTheDocument()
        expect(screen.getByText('2023')).toBeInTheDocument()
        expect(screen.getByText('Undated')).toBeInTheDocument()
        expect(screen.getByText('Dated')).toBeInTheDocument()
    })
})
