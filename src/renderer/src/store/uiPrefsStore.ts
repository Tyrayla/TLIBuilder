// Small persisted UI-preference store. Currently just the inert-modifier badge toggle; future
// renderer-only prefs can hang off here.
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// How a catalog list is ordered. Persisted so it sticks across sessions. ACTIVE skills always sort
// alphabetically (a per-skill DPS sort would be inaccurate — each is a different main skill); PASSIVE skills
// can sort by DPS contribution because they all buff the same equipped build, so the delta is comparable.
export type CatalogSort = 'alpha' | 'dps'

interface UiPrefsStore {
  // Show the per-modifier "Unused" / "Unrecognized" engine-coverage badges. Default ON.
  showModifierBadges: boolean
  toggleModifierBadges: () => void
  // Support catalog sort order. Default alphabetical; the user can opt into DPS-contribution sorting.
  supportSort: CatalogSort
  setSupportSort: (sort: CatalogSort) => void
  // Passive-skill catalog sort order (same options as supports; only used on passive slots).
  passiveSort: CatalogSort
  setPassiveSort: (sort: CatalogSort) => void
}

export const useUiPrefs = create<UiPrefsStore>()(
  persist(
    (set) => ({
      showModifierBadges: true,
      toggleModifierBadges: () => set((s) => ({ showModifierBadges: !s.showModifierBadges })),
      supportSort: 'alpha',
      setSupportSort: (supportSort) => set({ supportSort }),
      passiveSort: 'alpha',
      setPassiveSort: (passiveSort) => set({ passiveSort }),
    }),
    { name: 'tli-ui-prefs' },
  ),
)
