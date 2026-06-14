// Small persisted UI-preference store. Currently just the inert-modifier badge toggle; future
// renderer-only prefs can hang off here.
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// How the support catalog list is ordered. Persisted so it sticks across sessions. (Skills always
// sort alphabetically — a per-skill DPS sort would be inaccurate, so there's no DPS option for them.)
export type CatalogSort = 'alpha' | 'dps'

interface UiPrefsStore {
  // Show the per-modifier "Unused" / "Unrecognized" engine-coverage badges. Default ON.
  showModifierBadges: boolean
  toggleModifierBadges: () => void
  // Support catalog sort order. Default alphabetical; the user can opt into DPS-contribution sorting.
  supportSort: CatalogSort
  setSupportSort: (sort: CatalogSort) => void
}

export const useUiPrefs = create<UiPrefsStore>()(
  persist(
    (set) => ({
      showModifierBadges: true,
      toggleModifierBadges: () => set((s) => ({ showModifierBadges: !s.showModifierBadges })),
      supportSort: 'alpha',
      setSupportSort: (supportSort) => set({ supportSort }),
    }),
    { name: 'tli-ui-prefs' },
  ),
)
