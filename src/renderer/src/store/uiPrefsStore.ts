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
  // Stats screen: which skill slot is being viewed. Persisted so it sticks when navigating away and back
  // (a new/empty build falls back to the first populated slot via the screen's effect).
  statsSelectedSlot: number
  setStatsSelectedSlot: (slot: number) => void
  // Allow stat panels (StatPanel boxes) to collapse via their +/− control. Default OFF — boxes stay expanded
  // and show no collapse control; the user opts in under Settings → Display.
  collapsiblePanels: boolean
  setCollapsiblePanels: (on: boolean) => void
  // Stats skill area: show EVERY mechanic/ailment/CC box even when this skill can't use it (e.g. Multistrike on
  // a spell, Ignite on a non-hitting skill). Default OFF — boxes are skill-gated; the toggle reveals all.
  statsShowAllBoxes: boolean
  setStatsShowAllBoxes: (on: boolean) => void
  // Lock conditions the engine auto-inflicts (e.g. Splendor → Numbed/Frostbite/Ignite). Default OFF — auto-set
  // conditions show checked with an "auto" badge but stay editable so the user can override them. Turning it ON
  // locks them (the source guarantees them). Persisted across sessions.
  lockAutoConditions: boolean
  setLockAutoConditions: (on: boolean) => void
  // Global UI zoom (1 = 100%). Applied as CSS zoom on the document root so the whole interface scales uniformly
  // (fonts + spacing + icons), like browser zoom. Persisted across sessions.
  uiScale: number
  setUiScale: (scale: number) => void
  // Build sidebar width in px (user-draggable). Persisted across sessions.
  sidebarWidth: number
  setSidebarWidth: (px: number) => void
}

export const UI_SCALE_MIN = 0.8
export const UI_SCALE_MAX = 1.2
export const SIDEBAR_MIN = 140
export const SIDEBAR_MAX = 360
export const SIDEBAR_DEFAULT = 155

export const useUiPrefs = create<UiPrefsStore>()(
  persist(
    (set) => ({
      showModifierBadges: true,
      toggleModifierBadges: () => set((s) => ({ showModifierBadges: !s.showModifierBadges })),
      supportSort: 'alpha',
      setSupportSort: (supportSort) => set({ supportSort }),
      passiveSort: 'alpha',
      setPassiveSort: (passiveSort) => set({ passiveSort }),
      statsSelectedSlot: 1,
      setStatsSelectedSlot: (statsSelectedSlot) => set({ statsSelectedSlot }),
      collapsiblePanels: false,
      setCollapsiblePanels: (collapsiblePanels) => set({ collapsiblePanels }),
      statsShowAllBoxes: false,
      setStatsShowAllBoxes: (statsShowAllBoxes) => set({ statsShowAllBoxes }),
      lockAutoConditions: false,
      setLockAutoConditions: (lockAutoConditions) => set({ lockAutoConditions }),
      uiScale: 1,
      setUiScale: (uiScale) => set({ uiScale }),
      sidebarWidth: 155,
      setSidebarWidth: (sidebarWidth) => set({ sidebarWidth }),
    }),
    {
      name: 'tli-ui-prefs',
      // v1: lockAutoConditions' default flipped true→false. It was briefly persisted under the old default, so
      // drop any stored value once — the off-default then applies and the user's later choice persists normally.
      version: 1,
      migrate: (persisted, version) => {
        if (version < 1 && persisted && typeof persisted === 'object') {
          delete (persisted as { lockAutoConditions?: boolean }).lockAutoConditions
        }
        return persisted as UiPrefsStore
      },
    },
  ),
)
