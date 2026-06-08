// Small persisted UI-preference store. Currently just the inert-modifier badge toggle; future
// renderer-only prefs can hang off here.
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UiPrefsStore {
  // Show the per-modifier "Unused" / "Unrecognized" engine-coverage badges. Default ON.
  showModifierBadges: boolean
  toggleModifierBadges: () => void
}

export const useUiPrefs = create<UiPrefsStore>()(
  persist(
    (set) => ({
      showModifierBadges: true,
      toggleModifierBadges: () => set((s) => ({ showModifierBadges: !s.showModifierBadges })),
    }),
    { name: 'tli-ui-prefs' },
  ),
)
