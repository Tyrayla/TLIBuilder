// Regression coverage for the support-picker gating parser (client.ts: parseRequiredTags,
// isSupportCompatible, registerSkillTagVocabulary). See .wolf/buglog.json entry
// "support-gate-multiword-tag-word-split" for the bug this guards: Haunt ("Supports Shadow
// Strike Skills.") on Thunder Spike showed "No compatible supports" because the OLD parser
// whitespace-split the gate phrase into single words ("Shadow", "Strike") instead of matching
// the real multi-word skill_tag vocabulary ("Shadow Strike") as one unit.
//
// All skill/support tag shapes and gate phrasings below are copied verbatim from
// data/seasons/SS12/_skills.json (grepped, not invented) so these tests exercise the parser
// against real in-game wording rather than synthetic shapes built to fit the test — EXCEPT the
// case 6 fixture, which is explicitly a synthetic probe for the fail-closed drift guard (no real
// SS12 gate phrase currently contains an unresolvable word; see that case's comment).

import { describe, it, expect } from 'vitest'
import { isSupportCompatible, registerSkillTagVocabulary } from '../api/client'
import type { SkillItem, EquippedSkill } from '../api/client'

function skillItem(partial: Pick<SkillItem, 'item_id' | 'name' | 'skill_tags'> & { description_lines?: string[] }): SkillItem {
  const description_lines = partial.description_lines ?? []
  return {
    ...partial,
    description_lines,
    raw_text: description_lines.join(' '),
  }
}

// Parent skills are equipped in an active/passive slot as EquippedSkill, not SkillItem — mirrors
// how PlayerSkillsScreen / HeroTraitScreen construct the parentSkill argument to isSupportCompatible.
function asParent(item: SkillItem, slot = 1): EquippedSkill {
  return {
    slot,
    item_id: item.item_id,
    name: item.name,
    level: 20,
    skill_tags: item.skill_tags,
    description_lines: item.description_lines,
    supports: [],
  }
}

// ---- Real SS12 fixtures (data/seasons/SS12/_skills.json) ----------------------------------

// Case 1: the original bug report — Haunt gates on the two-word tag "Shadow Strike".
const HAUNT = skillItem({
  item_id: 'haunt', name: 'Haunt',
  skill_tags: ['Attack', 'Melee', 'Shadow Strike', 'Support'],
  description_lines: ['Supports Shadow Strike Skills.'],
})
const THUNDER_SPIKE = skillItem({
  item_id: 'thunder_spike', name: 'Thunder Spike',
  skill_tags: ['Attack', 'Lightning', 'Area', 'Melee', 'Shadow Strike'],
})

// Case 2: a genuine single-word gate that doesn't trip any of isSupportCompatible's early
// tag-exclusion special cases (Spirit Magus / Summon / Spell / Attack), so the assertion is
// isolated to parseRequiredTags' single-word vocabulary match.
const INCREASED_AREA = skillItem({
  item_id: 'increased_area', name: 'Increased Area',
  skill_tags: ['Area', 'Support'],
  description_lines: ['Supports Area Skills.'],
})
const WILT_SPIKE = skillItem({
  item_id: 'wilt_spike', name: 'Wilt Spike',
  skill_tags: ['Attack', 'Melee', 'Shadow Strike', 'Erosion', 'Area', 'Persistent'],
})
const AEGIS_OF_FIRE = skillItem({
  item_id: 'aegis_of_fire', name: 'Aegis of Fire',
  skill_tags: ['Spell', 'Persistent', 'Fire', 'Defensive'],
})

// Case 3: the pre-existing TAG_ALIASES rename ("Slash Strike" phrase -> "Slash-Strike" tag),
// exercised mid-phrase (as the second word of a two-tag gate) rather than as the whole clause.
const RAGING_SLASH = skillItem({
  item_id: 'raging_slash', name: 'Raging Slash',
  skill_tags: ['Support', 'Attack', 'Melee', 'Slash-Strike'],
  description_lines: ['Supports Melee Slash Strike Skills.'],
})
const BERSERKING_BLADE = skillItem({
  item_id: 'berserking_blade', name: 'Berserking Blade',
  skill_tags: ['Attack', 'Melee', 'Area', 'Physical', 'Slash-Strike', 'Persistent'],
})

// Case 4: another real two-word tag family, "Spirit Magus".
const FRIEND_OF_SPIRIT_MAGI = skillItem({
  item_id: 'friend_of_spirit_magi', name: 'Friend of Spirit Magi',
  skill_tags: ['Summon', 'Support', 'Spirit Magus'],
  description_lines: ['Supports Spirit Magus Skills.'],
})
const SUMMON_THUNDER_MAGUS = skillItem({
  item_id: 'summon_thunder_magus', name: 'Summon Thunder Magus',
  skill_tags: ['Spell', 'Summon', 'Lightning', 'Spirit Magus'],
})

// Case 5b: the "Duration" -> "Persistent" TAG_ALIASES entry (client.ts ~line 2059). Extended
// Duration's real gate prose is "Supports Duration Skills." with skill_tags ["Persistent",
// "Support"], but no skill in any season carries a literal "Duration" tag — the real tag family
// is "Persistent". Pre-fix, parseRequiredTags("Duration") fell through to the unmatched-word
// branch and checkTag() always failed closed, so Extended Duration was gated off every skill in
// the game, including genuinely Persistent-tagged ones like Aegis of Fire. This regression case
// guards the fix: it would FAIL before the 'Duration': 'Persistent' alias was added.
const EXTENDED_DURATION = skillItem({
  item_id: 'extended_duration', name: 'Extended Duration',
  skill_tags: ['Persistent', 'Support'],
  description_lines: ['Supports Duration Skills.'],
})

// Case 5: composite AND gate with a "skills that ..." predicate as one operand — real SS12
// phrasing found on both Pain Amplification and Shortened Duration.
const PAIN_AMPLIFICATION = skillItem({
  item_id: 'pain_amplification', name: 'Pain Amplification',
  skill_tags: ['Support', 'Persistent'],
  description_lines: ['Supports Persistent Skills and skills that can inflict Ailment.'],
})
// Persistent AND deals damage (Attack tag) -> both AND operands satisfied.
// (WILT_SPIKE above is reused here — it also carries 'Persistent'.)
const FIRE_LIZARD_DISTILLATE = skillItem({
  item_id: 'fire_lizard_distillate', name: 'Fire Lizard Distillate',
  skill_tags: ['Persistent', 'Elixir'], // Persistent, but no Attack/Spell/Minion/Summon tag
})

const REAL_SKILLS: SkillItem[] = [
  HAUNT, THUNDER_SPIKE, INCREASED_AREA, WILT_SPIKE, AEGIS_OF_FIRE,
  RAGING_SLASH, BERSERKING_BLADE, FRIEND_OF_SPIRIT_MAGI, SUMMON_THUNDER_MAGUS,
  PAIN_AMPLIFICATION, FIRE_LIZARD_DISTILLATE, EXTENDED_DURATION,
]

describe('support-picker gating parser (bug: support-gate-multiword-tag-word-split)', () => {
  describe('1. Haunt ("Supports Shadow Strike Skills.") on Thunder Spike — the original bug', () => {
    it('is compatible once the real two-word tag vocabulary is registered', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(HAUNT, asParent(THUNDER_SPIKE), false, 1)).toBe(true)
    })
  })

  describe('2. single-word gate ("Supports Area Skills.")', () => {
    it('is compatible with an Area-tagged skill', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(INCREASED_AREA, asParent(WILT_SPIKE), false, 1)).toBe(true)
    })

    it('is incompatible with a non-Area skill', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(INCREASED_AREA, asParent(AEGIS_OF_FIRE), false, 1)).toBe(false)
    })
  })

  describe('3. Slash-Strike alias mid-phrase ("Supports Melee Slash Strike Skills.")', () => {
    it('resolves "Melee" via the vocabulary and "Slash Strike" via TAG_ALIASES in the same gate', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(RAGING_SLASH, asParent(BERSERKING_BLADE), false, 1)).toBe(true)
    })
  })

  describe('4. another real two-word tag ("Supports Spirit Magus Skills.")', () => {
    it('is compatible with a Spirit-Magus-tagged skill', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(FRIEND_OF_SPIRIT_MAGI, asParent(SUMMON_THUNDER_MAGUS), false, 1)).toBe(true)
    })
  })

  describe('5. composite AND + predicate ("Persistent Skills and skills that can inflict Ailment.")', () => {
    it('is compatible when the parent satisfies both the tag AND the damage-dealing predicate', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(PAIN_AMPLIFICATION, asParent(WILT_SPIKE), false, 1)).toBe(true)
    })

    it('is incompatible when the parent has the tag but fails the predicate half (no Attack/Spell/Minion/Summon tag)', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(PAIN_AMPLIFICATION, asParent(FIRE_LIZARD_DISTILLATE), false, 1)).toBe(false)
    })
  })

  describe("5b. 'Duration' TAG_ALIASES fix (\"Supports Duration Skills.\" -> Persistent)", () => {
    it('is compatible with a Persistent-tagged skill (would FAIL pre-fix: "Duration" matched no real tag, gating Extended Duration off every skill)', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(EXTENDED_DURATION, asParent(AEGIS_OF_FIRE), false, 1)).toBe(true)
    })

    it('is incompatible with a non-Persistent skill (gate still discriminates)', () => {
      registerSkillTagVocabulary(REAL_SKILLS)
      expect(isSupportCompatible(EXTENDED_DURATION, asParent(THUNDER_SPIKE), false, 1)).toBe(false)
    })
  })

  describe('6. fail-closed drift guard', () => {
    // Synthetic probe, not real SS12 data: simulates a future season introducing a gate word the
    // registered vocabulary has no tag for (e.g. a rename the client hasn't caught up to yet).
    // parseRequiredTags falls back to treating the unresolved word as a literal single-word
    // "tag", which checkTag() then finds nowhere in the parent's real skill_tags — so the
    // support stays hidden. This is the DELIBERATE choice documented in client.ts (~line 2120):
    // a wrongly-hidden support is a much smaller failure than wrongly exposing an incompatible
    // one that could silently corrupt the DPS calc.
    const DRIFT_PROBE = skillItem({
      item_id: 'synthetic_drift_probe', name: 'Synthetic Drift Probe',
      skill_tags: ['Support'],
      description_lines: ['Supports Zzyzx Skills.'],
    })

    it('a gate word with no matching vocabulary tag fails closed (incompatible)', () => {
      registerSkillTagVocabulary(REAL_SKILLS) // 'Zzyzx' is absent from this real vocabulary too
      expect(isSupportCompatible(DRIFT_PROBE, asParent(THUNDER_SPIKE), false, 1)).toBe(false)
    })
  })

  describe('7. vocabulary lifecycle (registerSkillTagVocabulary not yet called / clearReferenceData reset)', () => {
    it('degrades to fail-closed for a multi-word tag gate when the vocabulary is empty', () => {
      // registerSkillTagVocabulary([]) is exactly what referenceStore.clearReferenceData() calls,
      // resetting the module cache to the pseudo-tag-only fallback (Active/Passive) — the same
      // state the module starts in before the first catalog load ever populates it. Without the
      // real "Shadow Strike" tag in the vocabulary, parseRequiredTags can't consume it as one
      // unit and falls back to single literal words ("Shadow", "Strike"), neither of which
      // equals any of Thunder Spike's actual tags -> checkTag fails -> incompatible.
      registerSkillTagVocabulary([])
      expect(isSupportCompatible(HAUNT, asParent(THUNDER_SPIKE), false, 1)).toBe(false)

      // Restore real vocabulary so this reset doesn't leak into any test file executed after
      // this one within the same vitest worker (registerSkillTagVocabulary is a module-level cache).
      registerSkillTagVocabulary(REAL_SKILLS)
    })
  })
})
