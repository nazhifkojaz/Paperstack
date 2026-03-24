/**
 * Tests for UI store.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useUIStore } from './uiStore'

describe('uiStore', () => {
  beforeEach(() => {
    // Reset store before each test
    useUIStore.getState().sidebarOpen = false
  })

  describe('initial state', () => {
    it('should have sidebar closed by default', () => {
      const state = useUIStore.getState()
      expect(state.sidebarOpen).toBe(false)
    })
  })

  describe('toggleSidebar', () => {
    it('should toggle sidebar open when closed', () => {
      const { toggleSidebar } = useUIStore.getState()
      toggleSidebar()
      const state = useUIStore.getState()
      expect(state.sidebarOpen).toBe(true)
    })

    it('should toggle sidebar closed when open', () => {
      // First open it
      useUIStore.getState().openSidebar()
      expect(useUIStore.getState().sidebarOpen).toBe(true)
      
      // Then toggle it
      const { toggleSidebar } = useUIStore.getState()
      toggleSidebar()
      const state = useUIStore.getState()
      expect(state.sidebarOpen).toBe(false)
    })
  })

  describe('openSidebar', () => {
    it('should open the sidebar', () => {
      const { openSidebar } = useUIStore.getState()
      openSidebar()
      const state = useUIStore.getState()
      expect(state.sidebarOpen).toBe(true)
    })
  })

  describe('closeSidebar', () => {
    it('should close the sidebar', () => {
      // First open it
      useUIStore.getState().openSidebar()
      expect(useUIStore.getState().sidebarOpen).toBe(true)
      
      // Then close it
      const { closeSidebar } = useUIStore.getState()
      closeSidebar()
      const state = useUIStore.getState()
      expect(state.sidebarOpen).toBe(false)
    })
  })
})