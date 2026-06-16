import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface OnboardingState {
  // Tour state
  hasSeenTour: boolean
  tourStep: number
  
  // Feature-specific onboarding flags
  hasSeenAnnotationTooltip: boolean
  hasSeenChatIntro: boolean
  hasSeenSettingsOnboarding: boolean
  hasSeenCitationHelp: boolean
  
  // Actions
  completeTour: () => void
  setTourStep: (step: number) => void
  markAnnotationTooltipSeen: () => void
  markChatIntroSeen: () => void
  markSettingsOnboardingSeen: () => void
  markCitationHelpSeen: () => void
  resetAllOnboarding: () => void
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      hasSeenTour: false,
      tourStep: 0,
      hasSeenAnnotationTooltip: false,
      hasSeenChatIntro: false,
      hasSeenSettingsOnboarding: false,
      hasSeenCitationHelp: false,

      completeTour: () => set({ hasSeenTour: true, tourStep: 0 }),
      setTourStep: (step) => set({ tourStep: step }),
      markAnnotationTooltipSeen: () => set({ hasSeenAnnotationTooltip: true }),
      markChatIntroSeen: () => set({ hasSeenChatIntro: true }),
      markSettingsOnboardingSeen: () => set({ hasSeenSettingsOnboarding: true }),
      markCitationHelpSeen: () => set({ hasSeenCitationHelp: true }),
      resetAllOnboarding: () => set({
        hasSeenTour: false,
        tourStep: 0,
        hasSeenAnnotationTooltip: false,
        hasSeenChatIntro: false,
        hasSeenSettingsOnboarding: false,
        hasSeenCitationHelp: false,
      }),
    }),
    {
      name: 'paperstack-onboarding',
      partialize: (state) => ({
        hasSeenTour: state.hasSeenTour,
        hasSeenAnnotationTooltip: state.hasSeenAnnotationTooltip,
        hasSeenChatIntro: state.hasSeenChatIntro,
        hasSeenSettingsOnboarding: state.hasSeenSettingsOnboarding,
        hasSeenCitationHelp: state.hasSeenCitationHelp,
      }),
    },
  ),
)
