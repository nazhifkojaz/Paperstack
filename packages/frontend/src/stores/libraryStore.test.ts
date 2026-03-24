import { describe, it, expect, beforeEach } from 'vitest'
import { useLibraryStore } from './libraryStore'

describe('libraryStore - selection state', () => {
  beforeEach(() => {
    // Reset store before each test
    useLibraryStore.setState({
      isSelectionMode: false,
      selectedPdfIds: new Set<string>(),
    })
  })

  describe('initial state', () => {
    it('should have selection mode off by default', () => {
      const state = useLibraryStore.getState()
      expect(state.isSelectionMode).toBe(false)
    })

    it('should have empty selection by default', () => {
      const state = useLibraryStore.getState()
      expect(state.selectedPdfIds.size).toBe(0)
    })
  })

  describe('setSelectionMode', () => {
    it('should activate selection mode', () => {
      const { setSelectionMode } = useLibraryStore.getState()
      setSelectionMode(true)
      expect(useLibraryStore.getState().isSelectionMode).toBe(true)
    })

    it('should deactivate selection mode', () => {
      useLibraryStore.setState({ isSelectionMode: true })
      const { setSelectionMode } = useLibraryStore.getState()
      setSelectionMode(false)
      expect(useLibraryStore.getState().isSelectionMode).toBe(false)
    })

    it('should clear selection when activating selection mode', () => {
      useLibraryStore.setState({
        selectedPdfIds: new Set(['pdf1', 'pdf2'])
      })
      const { setSelectionMode } = useLibraryStore.getState()
      setSelectionMode(true)
      expect(useLibraryStore.getState().selectedPdfIds.size).toBe(0)
    })
  })

  describe('togglePdfSelection', () => {
    it('should add PDF to selection when not selected', () => {
      const { togglePdfSelection } = useLibraryStore.getState()
      togglePdfSelection('pdf1')
      expect(useLibraryStore.getState().selectedPdfIds.has('pdf1')).toBe(true)
    })

    it('should remove PDF from selection when already selected', () => {
      useLibraryStore.setState({ selectedPdfIds: new Set(['pdf1']) })
      const { togglePdfSelection } = useLibraryStore.getState()
      togglePdfSelection('pdf1')
      expect(useLibraryStore.getState().selectedPdfIds.has('pdf1')).toBe(false)
    })
  })

  describe('selectAllVisible', () => {
    it('should select all provided PDF IDs', () => {
      const { selectAllVisible } = useLibraryStore.getState()
      selectAllVisible(['pdf1', 'pdf2', 'pdf3'])
      const state = useLibraryStore.getState()
      expect(state.selectedPdfIds.size).toBe(3)
      expect(state.selectedPdfIds.has('pdf1')).toBe(true)
      expect(state.selectedPdfIds.has('pdf2')).toBe(true)
      expect(state.selectedPdfIds.has('pdf3')).toBe(true)
    })

    it('should replace existing selection', () => {
      useLibraryStore.setState({ selectedPdfIds: new Set(['old1', 'old2']) })
      const { selectAllVisible } = useLibraryStore.getState()
      selectAllVisible(['new1', 'new2'])
      const state = useLibraryStore.getState()
      expect(state.selectedPdfIds.size).toBe(2)
      expect(state.selectedPdfIds.has('old1')).toBe(false)
      expect(state.selectedPdfIds.has('new1')).toBe(true)
    })
  })

  describe('clearSelection', () => {
    it('should clear all selections', () => {
      useLibraryStore.setState({
        selectedPdfIds: new Set(['pdf1', 'pdf2', 'pdf3'])
      })
      const { clearSelection } = useLibraryStore.getState()
      clearSelection()
      expect(useLibraryStore.getState().selectedPdfIds.size).toBe(0)
    })

    it('should not change selection mode', () => {
      useLibraryStore.setState({
        isSelectionMode: true,
        selectedPdfIds: new Set(['pdf1'])
      })
      const { clearSelection } = useLibraryStore.getState()
      clearSelection()
      expect(useLibraryStore.getState().isSelectionMode).toBe(true)
    })
  })
})
