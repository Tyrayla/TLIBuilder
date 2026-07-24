// Soft-invalidation slot gating (client.ts: computeSkillSlotEligibility, computeInvalidSkillSlots,
// isActiveSkillItem, isEquippedActiveSkillValid). Two game rules let a normally-passive-tagged skill
// occupy an ACTIVE slot (1-5): Steel Vanguard's "Knowledgeable" core talent (-> Focus skills) and
// Iris's "Vigilant Breeze" / "Merged Spirit Magi" base trait (-> Spirit Magus skills). When the
// enabling talent/trait is missing, the equipped skill is soft-invalidated: flagged, not removed.
//
// Skill ids/tags below are copied from data/seasons/SS12/_skills.json and the Steel Vanguard /
// Iris trait catalogs (grepped, not invented): flame_focus (['Area','Focus','Fire','Spell']),
// summon_thunder_magus (['Spell','Summon','Lightning','Spirit Magus']), cruelty
// (['Aura','Area','Attack']), focused_slash (an ordinary Attack skill). The talent id
// 'steel_vanguard_knowledgeable' and trait id 'vigilant_breeze' are the real
// display_name_key / trait_id values from data/seasons/SS12/steel_vanguard.json and
// _hero_traits.json.

import { describe, it, expect } from 'vitest'
import {
  computeSkillSlotEligibility, computeInvalidSkillSlots, isActiveSkillItem, isPassiveSkillItem,
  isEquippedActiveSkillValid, isSupportSkillItem,
} from '../api/client'
import type {
  SkillItem, EquippedSkill, TreeSlot, SavedSlate, EquippedGearItem, BeltBlend, PlacedPrism,
} from '../api/client'

function skillItem(partial: Pick<SkillItem, 'item_id' | 'name' | 'skill_tags'> & { description_lines?: string[] }): SkillItem {
  const description_lines = partial.description_lines ?? []
  return { ...partial, description_lines, raw_text: description_lines.join(' ') }
}

function equipped(partial: Pick<EquippedSkill, 'slot' | 'item_id' | 'name' | 'skill_tags'>): EquippedSkill {
  return { ...partial, level: 20, description_lines: [], supports: [] }
}

const KNOWLEDGEABLE_SLOT: TreeSlot = {
  treeName: 'Steel Vanguard',
  nodeStates: {},
  coreTalentSelections: { '1': 'steel_vanguard_knowledgeable' },
}
const OTHER_CORE_TALENT_SLOT: TreeSlot = {
  treeName: 'Steel Vanguard',
  nodeStates: {},
  coreTalentSelections: { '1': 'steel_vanguard_resistance' },
}

const FOCUS_SKILL_ITEM = skillItem({
  item_id: 'flame_focus', name: 'Flame Focus', skill_tags: ['Area', 'Focus', 'Fire', 'Spell'],
  description_lines: ['Activates Focus and gains a buff: +7% additional Fire Damage.'],
})
const SPIRIT_MAGUS_SKILL_ITEM = skillItem({
  item_id: 'summon_thunder_magus', name: 'Summon Thunder Magus',
  skill_tags: ['Spell', 'Summon', 'Lightning', 'Spirit Magus'],
})
const AURA_SKILL_ITEM = skillItem({
  item_id: 'cruelty', name: 'Cruelty', skill_tags: ['Aura', 'Area', 'Attack'],
})
const ATTACK_SKILL_ITEM = skillItem({
  item_id: 'focused_slash', name: 'Focused Slash', skill_tags: ['Attack', 'Melee'],
})

function focusSkillInSlot(slot: number): EquippedSkill {
  return equipped({ slot, item_id: FOCUS_SKILL_ITEM.item_id, name: FOCUS_SKILL_ITEM.name, skill_tags: FOCUS_SKILL_ITEM.skill_tags })
}
function spiritMagusSkillInSlot(slot: number): EquippedSkill {
  return equipped({ slot, item_id: SPIRIT_MAGUS_SKILL_ITEM.item_id, name: SPIRIT_MAGUS_SKILL_ITEM.name, skill_tags: SPIRIT_MAGUS_SKILL_ITEM.skill_tags })
}

describe('computeSkillSlotEligibility', () => {
  it('focusActiveEligible is true when Knowledgeable is the selected core talent in any slot', () => {
    const e = computeSkillSlotEligibility(null, [null, KNOWLEDGEABLE_SLOT])
    expect(e.focusActiveEligible).toBe(true)
  })

  it('focusActiveEligible is false when Steel Vanguard is present but a different core talent is selected', () => {
    const e = computeSkillSlotEligibility(null, [OTHER_CORE_TALENT_SLOT])
    expect(e.focusActiveEligible).toBe(false)
  })

  it('spiritMagusActiveEligible is true only for the Vigilant Breeze trait id', () => {
    expect(computeSkillSlotEligibility('vigilant_breeze', []).spiritMagusActiveEligible).toBe(true)
    expect(computeSkillSlotEligibility('some_other_trait', []).spiritMagusActiveEligible).toBe(false)
    expect(computeSkillSlotEligibility(null, []).spiritMagusActiveEligible).toBe(false)
  })
})

describe('computeInvalidSkillSlots', () => {
  it('returns [] when the enabling talent is present (Focus skill in an active slot)', () => {
    const eligibility = computeSkillSlotEligibility(null, [KNOWLEDGEABLE_SLOT])
    expect(computeInvalidSkillSlots([focusSkillInSlot(1)], eligibility)).toEqual([])
  })

  it('returns the slot index when the enabling talent is absent (Focus skill in an active slot)', () => {
    const eligibility = computeSkillSlotEligibility(null, [OTHER_CORE_TALENT_SLOT])
    expect(computeInvalidSkillSlots([focusSkillInSlot(3)], eligibility)).toEqual([3])
  })

  it('returns [] when the enabling trait is present (Spirit Magus skill in an active slot)', () => {
    const eligibility = computeSkillSlotEligibility('vigilant_breeze', [])
    expect(computeInvalidSkillSlots([spiritMagusSkillInSlot(2)], eligibility)).toEqual([])
  })

  it('returns the slot index when the enabling trait is absent (Spirit Magus skill in an active slot)', () => {
    const eligibility = computeSkillSlotEligibility(null, [])
    expect(computeInvalidSkillSlots([spiritMagusSkillInSlot(4)], eligibility)).toEqual([4])
  })

  it('flags multiple independently-invalid active slots at once, with no count cap', () => {
    const eligibility = computeSkillSlotEligibility(null, [])   // neither rule active
    const skills = [focusSkillInSlot(1), focusSkillInSlot(2), spiritMagusSkillInSlot(3)]
    expect(computeInvalidSkillSlots(skills, eligibility)).toEqual([1, 2, 3])
  })

  it('never flags a passive slot (6-9), even when the same skill would be invalid in an active slot', () => {
    const eligibility = computeSkillSlotEligibility(null, [OTHER_CORE_TALENT_SLOT])   // Knowledgeable absent
    expect(computeInvalidSkillSlots([focusSkillInSlot(6), focusSkillInSlot(9)], eligibility)).toEqual([])
  })

  it('does not flag an ordinary active-tagged skill regardless of eligibility state', () => {
    const eligibility = computeSkillSlotEligibility(null, [])
    const attack = equipped({ slot: 1, item_id: ATTACK_SKILL_ITEM.item_id, name: ATTACK_SKILL_ITEM.name, skill_tags: ATTACK_SKILL_ITEM.skill_tags })
    expect(computeInvalidSkillSlots([attack], eligibility)).toEqual([])
  })

  it('toggling the enabling talent off flips the slot to invalid without removing or mutating the equipped skills array', () => {
    const skills = [focusSkillInSlot(1), equipped({ slot: 3, item_id: ATTACK_SKILL_ITEM.item_id, name: ATTACK_SKILL_ITEM.name, skill_tags: ATTACK_SKILL_ITEM.skill_tags })]
    const snapshotBefore = JSON.parse(JSON.stringify(skills))

    const withTalent = computeSkillSlotEligibility(null, [KNOWLEDGEABLE_SLOT])
    expect(computeInvalidSkillSlots(skills, withTalent)).toEqual([])
    expect(skills).toEqual(snapshotBefore)   // unaffected by computing eligibility/invalid slots

    const withoutTalent = computeSkillSlotEligibility(null, [OTHER_CORE_TALENT_SLOT])
    const invalid = computeInvalidSkillSlots(skills, withoutTalent)
    expect(invalid).toEqual([1])
    // The skill must still be there, untouched — soft-invalidation never strips or edits the equipped skill.
    expect(skills.length).toBe(2)
    expect(skills).toEqual(snapshotBefore)
    expect(skills[0].item_id).toBe(FOCUS_SKILL_ITEM.item_id)
  })
})

describe('isEquippedActiveSkillValid', () => {
  it('mirrors computeInvalidSkillSlots for a single skill_tags array', () => {
    const eligibility = computeSkillSlotEligibility(null, [])
    expect(isEquippedActiveSkillValid(FOCUS_SKILL_ITEM.skill_tags, eligibility)).toBe(false)
    expect(isEquippedActiveSkillValid(ATTACK_SKILL_ITEM.skill_tags, eligibility)).toBe(true)
  })
})

describe('isActiveSkillItem backward compatibility (called without an eligibility argument)', () => {
  it('a Focus-tagged skill is inactive with no eligibility passed, matching legacy static isPassiveSkillItem gating', () => {
    expect(isPassiveSkillItem(FOCUS_SKILL_ITEM)).toBe(true)
    expect(isActiveSkillItem(FOCUS_SKILL_ITEM)).toBe(false)
  })

  it('a Spirit-Magus-tagged skill is inactive with no eligibility passed', () => {
    expect(isActiveSkillItem(SPIRIT_MAGUS_SKILL_ITEM)).toBe(false)
  })

  it('an ordinary active-tagged skill is active with no eligibility passed', () => {
    expect(isActiveSkillItem(ATTACK_SKILL_ITEM)).toBe(true)
  })

  it('an Aura-tagged skill is inactive even WITH both eligibility flags true — Aura has no exemption rule at all', () => {
    expect(isActiveSkillItem(AURA_SKILL_ITEM, { focusActiveEligible: true, spiritMagusActiveEligible: true })).toBe(false)
  })

  it('passing eligibility only flips Focus/Spirit-Magus admissibility, leaving every other classification identical to the no-arg call', () => {
    // Explicit NO_SLOT_ELIGIBILITY-equivalent call must equal the omitted-argument call for every fixture.
    const noEligibility = { focusActiveEligible: false, spiritMagusActiveEligible: false }
    for (const item of [FOCUS_SKILL_ITEM, SPIRIT_MAGUS_SKILL_ITEM, AURA_SKILL_ITEM, ATTACK_SKILL_ITEM]) {
      expect(isActiveSkillItem(item, noEligibility)).toBe(isActiveSkillItem(item))
    }
  })
})

// ── Widened detection (post-accuracy-review) ──────────────────────────────────────────────────────
// 1. MERGED_SPIRIT_MAGI_TRAIT_IDS now includes both Iris base traits (was vigilant_breeze only).
// 2. computeSkillSlotEligibility gained an optional 3rd `sources` param covering three more Knowledgeable
//    grant paths beyond the talent tree: a slate isCore slot, a legendary gear bracket affix, a belt blend,
//    and a REPLACE-type Ethereal Prism — mirroring core_talent_resolver.py's `_collect` (+ prism_core_talents.py).
// Shapes below are lifted from the real SS12 catalogs (data/seasons/SS12/_belt_blends.json talent shape,
// _legendary_gear.json bracket-affix convention, _ethereal_prism.json implicit phrasing) — no current-season
// entry actually grants "Knowledgeable" via gear/belt/prism, so the talent NAME itself is a stand-in for the
// forward-compat path the source comments call out, but the surrounding JSON shape is real.

const KNOWLEDGEABLE_SLATE: SavedSlate = {
  id: 'slate-1', kind: 'medium', cells: [[0, 0]], orientationIndex: 0, shapeIndex: 0, anchor: [0, 0],
  slots: [{
    slotType: 'legendary', maxType: 'legendary', canBeCore: true, isCore: true,
    selectedNodeId: 'node-1', selectedCoreKey: 'knowledgeable', coreName: 'Knowledgeable', effects: [],
  }],
}

// Bracket-affix convention confirmed against real entries in data/seasons/SS12/_legendary_gear.json, e.g.
// Endless Fortress: "[Ward] Adds 13 % of Sealed Mana as Energy Shield".
const KNOWLEDGEABLE_GEAR_ITEM: EquippedGearItem = {
  item_id: 'test_legendary_grip', name: 'Test Legendary Grip', required_level: 58,
  affixes: [{
    raw_text: '[Knowledgeable] Focus Skills can be equipped to Active Skill slots',
    modifier_id: null, expression: '[Knowledgeable] Focus Skills can be equipped to Active Skill slots',
    condition: null, affix_kind: 'special', numeric_values: [],
  }],
  customizations: [], slot: 'chest',
}

// Belt-blend shape confirmed against a real core-type entry in data/seasons/SS12/_belt_blends.json
// (talent_id "350001" / talent_name "Elimination" / talent_type "core") — same shape, substituted name.
const KNOWLEDGEABLE_BELT_BLEND: BeltBlend = {
  talent_id: '350099', talent_type: 'core', talent_level: 0, talent_name: 'Knowledgeable',
  effect_text: 'Focus Skills can be equipped to Active Skill slots',
  effect_raw: '[Knowledgeable] Focus Skills can be equipped to Active Skill slots',
}
const BELT_ITEM_WITH_KNOWLEDGEABLE_BLEND: EquippedGearItem = {
  item_id: 'test_belt', name: 'Test Belt', required_level: 1, affixes: [], customizations: [],
  slot: 'belt', beltBlend: '350099',
}

// Implicit phrasing confirmed against data/seasons/SS12/_ethereal_prism.json base_affixes, e.g. "Replaces the
// Core Talent on the God of Might/.../God of Machines Advanced Talent Panel with One For All".
const KNOWLEDGEABLE_PRISM: PlacedPrism = {
  id: 'prism-1', templateId: 'ethereal_prism_test', kind: 'ethereal_prism', name: 'Ethereal Prism: Test',
  iconUrl: '', rolls: { micro: 0, medium: 0, legendary: 0 },
  ethereal: {
    shortName: 'Knowledgeable', rarity: 'legendary',
    implicit: 'Replaces the Core Talent on the Steel Vanguard Advanced Talent Panel with Knowledgeable',
    tintWhenRare: false,
  },
  treeName: 'Steel Vanguard', anchorCol: 0, anchorRow: 0, boxAllocations: {},
}
const HIGH_POINTS_SLOT: TreeSlot = { treeName: 'Steel Vanguard', nodeStates: { '1': 12, '2': 12 } } // sums to 24
const LOW_POINTS_SLOT: TreeSlot = { treeName: 'Steel Vanguard', nodeStates: { '1': 5 } }

// Real support skill from data/seasons/SS12/_skills.json — item_id 'focus_buff', skill_type 'support_skill',
// tagged [Support, Focus]. The bug-226 case: a support carrying a passive tag must never be treated as an
// active-slot-eligible skill, no matter how eligibility resolves.
const FOCUS_BUFF_SUPPORT_ITEM: SkillItem = {
  item_id: 'focus_buff', name: 'Focus Buff', skill_type: 'support_skill', skill_tags: ['Support', 'Focus'],
  description_lines: ['Supports Focus Skills.'], raw_text: 'Supports Focus Skills.',
}

describe('Iris Merged Spirit Magi — both base traits widen spiritMagusActiveEligible', () => {
  it('growing_breeze sets spiritMagusActiveEligible true, and a Spirit Magus skill in an active slot under it is NOT flagged invalid (regression: previously wrongly invalidated)', () => {
    const eligibility = computeSkillSlotEligibility('growing_breeze', [])
    expect(eligibility.spiritMagusActiveEligible).toBe(true)
    expect(computeInvalidSkillSlots([spiritMagusSkillInSlot(2)], eligibility)).toEqual([])
  })

  it('vigilant_breeze still works (no regression), and an unrelated trait id still yields false', () => {
    expect(computeSkillSlotEligibility('vigilant_breeze', []).spiritMagusActiveEligible).toBe(true)
    expect(computeInvalidSkillSlots([spiritMagusSkillInSlot(2)], computeSkillSlotEligibility('vigilant_breeze', []))).toEqual([])
    expect(computeSkillSlotEligibility('some_other_trait', []).spiritMagusActiveEligible).toBe(false)
  })
})

describe('computeSkillSlotEligibility — Knowledgeable via the four widened grant sources', () => {
  it('a slate slot flagged isCore with coreName "Knowledgeable" grants focusActiveEligible', () => {
    const e = computeSkillSlotEligibility(null, [], { slates: [KNOWLEDGEABLE_SLATE] })
    expect(e.focusActiveEligible).toBe(true)
  })

  it('a legendary gear bracket affix "[Knowledgeable] …" grants focusActiveEligible', () => {
    const e = computeSkillSlotEligibility(null, [], { gear: [KNOWLEDGEABLE_GEAR_ITEM] })
    expect(e.focusActiveEligible).toBe(true)
  })

  it('an equipped belt blend resolving to talent_name "Knowledgeable" grants focusActiveEligible (needs both gear and the beltBlends catalog)', () => {
    const e = computeSkillSlotEligibility(null, [], {
      gear: [BELT_ITEM_WITH_KNOWLEDGEABLE_BLEND], beltBlends: [KNOWLEDGEABLE_BELT_BLEND],
    })
    expect(e.focusActiveEligible).toBe(true)

    // Documented degrade: without the beltBlends catalog, the belt-blend source contributes nothing
    // (not a crash, not a false positive).
    const eNoCatalog = computeSkillSlotEligibility(null, [], { gear: [BELT_ITEM_WITH_KNOWLEDGEABLE_BLEND] })
    expect(eNoCatalog.focusActiveEligible).toBe(false)
  })

  it('a REPLACE-type Ethereal Prism named "Knowledgeable" at >=24 tree points grants focusActiveEligible', () => {
    const e = computeSkillSlotEligibility(null, [HIGH_POINTS_SLOT], { prisms: [KNOWLEDGEABLE_PRISM] })
    expect(e.focusActiveEligible).toBe(true)
  })

  it('the same prism below the 24-point threshold does not grant Knowledgeable', () => {
    const e = computeSkillSlotEligibility(null, [LOW_POINTS_SLOT], { prisms: [KNOWLEDGEABLE_PRISM] })
    expect(e.focusActiveEligible).toBe(false)
  })
})

describe('computeSkillSlotEligibility — 2-arg call is unaffected (backward compatibility)', () => {
  it('omitting sources reproduces identical output to an explicit empty sources object, for every trait/slot combo', () => {
    const cases: [string | null, (TreeSlot | null)[]][] = [
      [null, []],
      ['vigilant_breeze', []],
      ['growing_breeze', []],
      [null, [KNOWLEDGEABLE_SLOT]],
      [null, [OTHER_CORE_TALENT_SLOT]],
    ]
    for (const [traitId, slots] of cases) {
      expect(computeSkillSlotEligibility(traitId, slots)).toEqual(computeSkillSlotEligibility(traitId, slots, {}))
    }
  })
})

describe('computeInvalidSkillSlots — both exemptions active simultaneously', () => {
  it('Focus and Spirit Magus skills in active slots are legal under Knowledgeable + an Iris trait together; a genuinely illegal Aura skill in an active slot is still flagged (Aura has no exemption rule at all)', () => {
    const eligibility = computeSkillSlotEligibility('growing_breeze', [KNOWLEDGEABLE_SLOT])
    expect(eligibility.focusActiveEligible).toBe(true)
    expect(eligibility.spiritMagusActiveEligible).toBe(true)

    const skills = [
      focusSkillInSlot(1),
      spiritMagusSkillInSlot(2),
      equipped({ slot: 3, item_id: AURA_SKILL_ITEM.item_id, name: AURA_SKILL_ITEM.name, skill_tags: AURA_SKILL_ITEM.skill_tags }),
    ]
    expect(computeInvalidSkillSlots(skills, eligibility)).toEqual([3])
  })
})

describe('isActiveSkillItem — a Support skill carrying a passive tag is never active-slot eligible (bug-226 short-circuit)', () => {
  it('Focus Buff (real support skill tagged [Support, Focus]) is excluded from active slots even when focusActiveEligible is true', () => {
    expect(isSupportSkillItem(FOCUS_BUFF_SUPPORT_ITEM)).toBe(true)
    expect(isActiveSkillItem(FOCUS_BUFF_SUPPORT_ITEM, { focusActiveEligible: true, spiritMagusActiveEligible: true })).toBe(false)
  })
})

describe('computeInvalidSkillSlots — passive slots (6-9) are never flagged, regardless of eligibility source', () => {
  it('a Focus skill in slots 6/9 is never flagged with no sources active', () => {
    const eligibility = computeSkillSlotEligibility(null, [])
    expect(computeInvalidSkillSlots([focusSkillInSlot(6), focusSkillInSlot(9)], eligibility)).toEqual([])
  })

  it('a Spirit Magus / Focus skill in slots 7/8 is never flagged even with both exemptions granted via widened sources', () => {
    const eligibility = computeSkillSlotEligibility('growing_breeze', [], { gear: [KNOWLEDGEABLE_GEAR_ITEM] })
    expect(computeInvalidSkillSlots([spiritMagusSkillInSlot(7), focusSkillInSlot(8)], eligibility)).toEqual([])
  })
})
