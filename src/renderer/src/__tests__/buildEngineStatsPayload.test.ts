import { describe, it, expect, beforeEach } from 'vitest'
import { buildEngineStatsPayload } from '../utils/statsPayload'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import type { EquippedSkill, EquippedSupportSkill, PactSpirit, SelectedPactSpirit } from '../api/client'

function skill(partial: Partial<EquippedSkill>): EquippedSkill {
  return { slot: 1, item_id: 'skill', name: 'Skill', level: 20, skill_tags: [], description_lines: [], supports: [], ...partial }
}
function support(partial: Partial<EquippedSupportSkill>): EquippedSupportSkill {
  return {
    support_index: 1, item_id: 'sup', name: 'Sup', skill_type: 'support_skill', level: 20,
    skill_tags: [], description_lines: [], ...partial,
  }
}

// Full base BuildState snapshot to override per test — guarantees type correctness against
// ReturnType<typeof useBuildStore.getState> without hand-rolling every field.
const base = useBuildStore.getState()

beforeEach(() => {
  useReferenceStore.setState({ heroTraits: [] })
})

describe('buildEngineStatsPayload — _traitSkillActive gating (Rosa Holy Domain synthetic slot)', () => {
  it('grants the synthetic slot-10 skill + its supports when the trait grants the slot AND supports are socketed', () => {
    const s = {
      ...base,
      traitId: 'high_court_chariot',
      advancedTraitSelections: ['Invulnerability'],
      traitSkillSupports: [support({ item_id: 'holy_sup' })],
    }
    const payload = buildEngineStatsPayload(s)
    expect(payload.skills.some((sk) => sk.slot === 10 && sk.skill_id === 'rosa_holy_domain')).toBe(true)
    expect(payload.attached_supports.some((a) => a.slot === 10 && a.item_id === 'holy_sup')).toBe(true)
  })

  it('does NOT grant the synthetic slot when the trait grants it but NO supports are socketed', () => {
    const s = { ...base, traitId: 'high_court_chariot', advancedTraitSelections: ['Invulnerability'], traitSkillSupports: [] }
    const payload = buildEngineStatsPayload(s)
    expect(payload.skills.some((sk) => sk.slot === 10)).toBe(false)
    expect(payload.attached_supports.some((a) => a.slot === 10)).toBe(false)
  })

  it('does NOT grant the synthetic slot for a different trait even with supports socketed', () => {
    const s = { ...base, traitId: 'unsullied_blade', advancedTraitSelections: [], traitSkillSupports: [support({ item_id: 'holy_sup' })] }
    const payload = buildEngineStatsPayload(s)
    expect(payload.skills.some((sk) => sk.slot === 10)).toBe(false)
  })
})

describe('buildEngineStatsPayload — _excludeOnce (spiritEffectExclude)', () => {
  it('removes exactly ONE occurrence of a duplicated effect text; the other survives', () => {
    // Two selected spirit slots, neither with an Undetermined Fate installed → each emits the SAME generic
    // "+6 % Damage" / "+6 % Minion Damage" pair (source: 'Pact: Undetermined'). A natural duplicate-text source.
    const spiritA = { item_id: 'spirit_a', name: 'Spirit A', slots: [], upgrade_ranks: [] } as unknown as PactSpirit
    const selected: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null] = [
      { itemId: 'spirit_a', rank: 1 },
      { itemId: 'spirit_a', rank: 1 },
      null,
    ]
    const s = {
      ...base,
      allSpirits: [spiritA],
      pactSpirits: selected,
      fates: {},
      undetermined: [null, null, null] as [null, null, null],
      spiritEffectExclude: ['+6 % Damage'],
    }
    const payload = buildEngineStatsPayload(s)
    const dmgTexts = payload.spirit_effects.filter((e) => e.text === '+6 % Damage')
    const minionTexts = payload.spirit_effects.filter((e) => e.text === '+6 % Minion Damage')
    expect(dmgTexts.length).toBe(1)      // 2 emitted, 1 excluded → 1 survives
    expect(minionTexts.length).toBe(2)   // untouched — not in the exclude list
  })
})

describe('buildEngineStatsPayload — elixir_ingredients flattening', () => {
  it('drops empty-string ingredient slots (Boolean filter) but keeps the slot key with an empty array', () => {
    const s = {
      ...base,
      elixirIngredients: { 0: { potency: 'Ingredient A', flavor: '' }, 1: {} },
    }
    const payload = buildEngineStatsPayload(s)
    expect(payload.elixir_ingredients).toEqual({ '0': ['Ingredient A'], '1': [] })
  })
})

describe('buildEngineStatsPayload — enabled !== false defaulting', () => {
  it('skills: undefined enabled defaults to true; explicit false/true pass through', () => {
    const s = {
      ...base,
      skills: [
        skill({ slot: 1, item_id: 'implicit_true', enabled: undefined }),
        skill({ slot: 2, item_id: 'explicit_false', enabled: false }),
        skill({ slot: 3, item_id: 'explicit_true', enabled: true }),
      ],
    }
    const payload = buildEngineStatsPayload(s)
    const byId = Object.fromEntries(payload.skills.map((sk) => [sk.skill_id, sk.enabled]))
    expect(byId.implicit_true).toBe(true)
    expect(byId.explicit_false).toBe(false)
    expect(byId.explicit_true).toBe(true)
  })

  it('attached_supports: undefined enabled defaults to true; explicit false passes through', () => {
    const s = {
      ...base,
      skills: [
        skill({
          slot: 1, item_id: 'host',
          supports: [support({ item_id: 'sup_implicit', enabled: undefined }), support({ item_id: 'sup_disabled', enabled: false })],
        }),
      ],
    }
    const payload = buildEngineStatsPayload(s)
    const byId = Object.fromEntries(payload.attached_supports.map((a) => [a.item_id, a.enabled]))
    expect(byId.sup_implicit).toBe(true)
    expect(byId.sup_disabled).toBe(false)
  })
})
