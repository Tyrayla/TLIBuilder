import { describe, it, expect, beforeEach } from 'vitest'
import { useBuildStore } from '../store/buildStore'
import type { LoadedBuild } from '../store/buildStore'
import { EMPTY_STAT_SHEET } from '../api/client'
import type { EquippedSkill, Loadout, PactSpirit, StatSheetResponse } from '../api/client'
import { DEFAULT_TARGET_CONFIG } from '../utils/targetPresets'

// Full initial snapshot (captured before any test mutates the singleton store) — used to fully
// reset the store between tests via setState(initial, true) (replace).
const initialState = useBuildStore.getState()

beforeEach(() => {
  useBuildStore.setState(initialState, true)
})

function skill(partial: Partial<EquippedSkill>): EquippedSkill {
  return { slot: 1, item_id: 'skill', name: 'Skill', level: 20, skill_tags: [], description_lines: [], supports: [], ...partial }
}

const baseLoadedBuild: LoadedBuild = {
  buildId: 'b1', buildName: 'Test Build', activeSlot: 0,
  slots: [null, null, null, null], slates: [], slateInventory: [], prisms: [], prismInventory: [],
  conditionState: {}, gear: [], skills: [], characterLevel: 100,
  traitId: null, traitSlotLevels: [1, 1, 1, 1], advancedTraitSelections: [], traitSkillSupports: [],
  licoricePreparedSkill: null, elixirIngredients: {},
  heroMemories: [null, null, null], pactSpirits: [null, null, null],
  fates: {}, undetermined: [null, null, null], notes: '', customMods: [],
  targetConfig: DEFAULT_TARGET_CONFIG, loadouts: [], activeLoadoutId: '',
}

describe('deriveMainSkill (via setSkills)', () => {
  it('filters out slots > 5 (passive slots never become mainSkill)', () => {
    useBuildStore.getState().setSkills([
      skill({ slot: 6, item_id: 'passive_only' }),
    ])
    expect(useBuildStore.getState().mainSkill).toBeNull()
  })

  it('filters out enabled === false skills', () => {
    useBuildStore.getState().setSkills([
      skill({ slot: 1, item_id: 'disabled_one', enabled: false }),
      skill({ slot: 2, item_id: 'active_two' }),
    ])
    expect(useBuildStore.getState().mainSkill).toEqual({ skill_id: 'active_two', level: 20 })
  })

  it('prefers slot 1 when present', () => {
    useBuildStore.getState().setSkills([
      skill({ slot: 3, item_id: 'slot_three' }),
      skill({ slot: 1, item_id: 'slot_one' }),
    ])
    expect(useBuildStore.getState().mainSkill).toEqual({ skill_id: 'slot_one', level: 20 })
  })

  it('falls back to the lowest active slot when slot 1 is empty', () => {
    useBuildStore.getState().setSkills([
      skill({ slot: 4, item_id: 'slot_four' }),
      skill({ slot: 2, item_id: 'slot_two' }),
    ])
    expect(useBuildStore.getState().mainSkill).toEqual({ skill_id: 'slot_two', level: 20 })
  })

  it('all skills disabled → mainSkill is null', () => {
    useBuildStore.getState().setSkills([
      skill({ slot: 1, item_id: 'a', enabled: false }),
      skill({ slot: 2, item_id: 'b', enabled: false }),
    ])
    expect(useBuildStore.getState().mainSkill).toBeNull()
  })
})

describe('deriveMainSkill (via loadBuild)', () => {
  it('derives mainSkill from the loaded skills array the same way setSkills does', () => {
    useBuildStore.getState().loadBuild({
      ...baseLoadedBuild,
      skills: [skill({ slot: 2, item_id: 'loaded_main' }), skill({ slot: 6, item_id: 'loaded_passive' })],
    })
    expect(useBuildStore.getState().mainSkill).toEqual({ skill_id: 'loaded_main', level: 20 })
  })

  it('resets computedStats to EMPTY_STAT_SHEET and clears loadoutStatsCache', () => {
    useBuildStore.setState({
      computedStats: { note: 'stale-stats' } as unknown as StatSheetResponse,
      loadoutStatsCache: { someLoadout: { stats: {} as StatSheetResponse, key: 'k' } },
    })
    useBuildStore.getState().loadBuild(baseLoadedBuild)
    const s = useBuildStore.getState()
    expect(s.computedStats).toBe(EMPTY_STAT_SHEET)
    expect(s.loadoutStatsCache).toEqual({})
  })
})

describe('resolved-once guard: setAllSpirits / setSpiritsFailure', () => {
  const spiritA = { item_id: 'spirit_a', name: 'Spirit A', slots: [], upgrade_ranks: [] } as unknown as PactSpirit

  it('success-then-failure: once resolved via success, a later failure call is a no-op', () => {
    useBuildStore.getState().setAllSpirits([spiritA])
    const afterSuccess = useBuildStore.getState()
    expect(afterSuccess.spiritsResolved).toBe(true)
    expect(afterSuccess.spiritsFetchFailed).toBe(false)
    const versionAfterSuccess = afterSuccess.buildVersion

    useBuildStore.getState().setSpiritsFailure()
    const afterFailure = useBuildStore.getState()
    // Guard: `if (s.spiritsResolved) return s` — already resolved, so the failure call changes nothing.
    expect(afterFailure.spiritsFetchFailed).toBe(false)
    expect(afterFailure.buildVersion).toBe(versionAfterSuccess)
    expect(afterFailure.allSpirits).toEqual([spiritA])
  })

  it('failure-then-success: once resolved via failure, a later success call with the SAME (empty) data is a no-op', () => {
    useBuildStore.getState().setSpiritsFailure()
    const afterFailure = useBuildStore.getState()
    expect(afterFailure.spiritsResolved).toBe(true)
    expect(afterFailure.spiritsFetchFailed).toBe(true)
    const versionAfterFailure = afterFailure.buildVersion

    // allSpirits is still [] (the default) at this point — passing [] again is content-equal, so the
    // `isEqual` no-op guard fires and the failure flag survives untouched.
    useBuildStore.getState().setAllSpirits([])
    const afterSuccess = useBuildStore.getState()
    expect(afterSuccess.spiritsFetchFailed).toBe(true)
    expect(afterSuccess.buildVersion).toBe(versionAfterFailure)
  })
})

describe('loadouts: cache-fingerprint HIT vs MISS', () => {
  const skillA = skill({ slot: 1, item_id: 'a' })
  const skillB = skill({ slot: 1, item_id: 'b' })
  const loadoutA: Loadout = { id: 'A', name: 'A', data: { skills: { skills: [skillA] } }, inherit: {} }
  const loadoutB: Loadout = { id: 'B', name: 'B', data: { skills: { skills: [skillB] } }, inherit: {} }

  beforeEach(() => {
    useBuildStore.setState({
      loadouts: [loadoutA, loadoutB],
      activeLoadoutId: 'A',
      skills: [skillA],
      mainSkill: { skill_id: 'a', level: 20 },
    })
  })

  it('MISS: switching to a loadout with no cache entry leaves computedVersion behind buildVersion (recompute needed)', () => {
    useBuildStore.getState().switchLoadout('B')
    const s = useBuildStore.getState()
    expect(s.activeLoadoutId).toBe('B')
    expect(s.skills).toEqual([skillB])
    expect(s.computedVersion).toBeLessThan(s.buildVersion)
  })

  it('HIT: switching to a loadout whose cached fingerprint matches applies the cached stats immediately (no recompute)', () => {
    useBuildStore.getState().switchLoadout('B')
    const fakeStatsForB = { note: 'stats-for-B' } as unknown as StatSheetResponse
    useBuildStore.getState().cacheActiveLoadoutStats(fakeStatsForB)

    // Swap away and back — nothing about B changed, so the fingerprint still matches.
    useBuildStore.getState().switchLoadout('A')
    useBuildStore.getState().switchLoadout('B')

    const s = useBuildStore.getState()
    expect(s.computedStats).toBe(fakeStatsForB)
    expect(s.computedVersion).toBe(s.buildVersion)
  })
})

describe('editLoadouts', () => {
  it('re-syncs mainSkill after an inherited skills-link is removed from the active loadout', () => {
    const mainA = skill({ slot: 1, item_id: 'main_a' })
    const loadoutA: Loadout = { id: 'A', name: 'A', data: { skills: { skills: [mainA] } }, inherit: {} }
    const loadoutB: Loadout = { id: 'B', name: 'B', data: {}, inherit: { skills: 'A' } }
    useBuildStore.setState({
      loadouts: [loadoutA, loadoutB],
      activeLoadoutId: 'A',
      skills: [mainA],
      mainSkill: { skill_id: 'main_a', level: 20 },
    })

    useBuildStore.getState().switchLoadout('B')
    expect(useBuildStore.getState().mainSkill).toEqual({ skill_id: 'main_a', level: 20 }) // inherited from A

    useBuildStore.getState().editLoadouts((loadouts) =>
      loadouts.map((l) => (l.id === 'B' ? { ...l, inherit: {}, data: { ...l.data, skills: { skills: [] } } } : l)),
    )

    const s = useBuildStore.getState()
    expect(s.skills).toEqual([])
    expect(s.mainSkill).toBeNull()
  })
})
