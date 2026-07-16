import {
  EquippedGearItem, GearSlot, GearEngineItem, GearAffixContribution, CraftBaseItemGroup,
  LegendaryAffix, CustomizedAffix, EffectInput,
  buildCharacterContributions, buildMemoryEffects, buildSpiritEffects, buildTraitEffects, withGuaranteedPicks,
  traitGrantsSkillSlot, TRAIT_SKILL_SLOT, TRAIT_SKILL_ID,
} from '../api/client'
import { itemHasSlot } from './gearItem'
import { characterLevelFrom } from './conditions'
import { DAMAGE_TYPES } from './damageTypes'
import { useReferenceStore } from '../store/referenceStore'
import type { useBuildStore } from '../store/buildStore'

export { buildCharacterContributions, buildMemoryEffects, buildSpiritEffects, buildTraitEffects }

export type BuildState = ReturnType<typeof useBuildStore.getState>

// Effective hero-trait picks for the engine payload = user picks + always-granted guaranteed nodes (enabled tiers).
function _effTraitPicks(s: BuildState): string[] {
  return withGuaranteedPicks(s.traitId, s.traitSlotLevels, s.advancedTraitSelections,
    useReferenceStore.getState().heroTraits ?? [])
}

// Dual wielding = both weapon slots hold a WEAPON (not a shield, and not a 2H which only fills
// weapon1). Drives the auto-set `dual_wielding` condition (the engine grants its base effects).
function isShieldItem(item: EquippedGearItem): boolean {
  return /shield/i.test(item.base_type ?? '')
}
export function isDualWielding(gear: EquippedGearItem[]): boolean {
  const w1 = gear.find(i => itemHasSlot(i, 'weapon1'))
  const w2 = gear.find(i => itemHasSlot(i, 'weapon2'))
  return !!w1 && !!w2 && !isShieldItem(w1) && !isShieldItem(w2)
}

// base-item-name → weapon-class map, built from the prefetched craft base-items catalog
// (e.g. "Battlefield Longsword" → "one_handed_sword", "Blue Sea Greataxe" → "two_handed_axe").
// Memoized by the catalog array reference so it rebuilds only when the reference data changes.
let _weaponClassCache: { groups: CraftBaseItemGroup[]; map: Map<string, string> } | null = null
function weaponClassMap(): Map<string, string> {
  const groups = useReferenceStore.getState().craftBaseItems ?? []
  if (_weaponClassCache && _weaponClassCache.groups === groups) return _weaponClassCache.map
  const map = new Map<string, string>()
  for (const g of groups) {
    for (const bi of g.base_items) map.set(bi.name, g.item_id)
  }
  _weaponClassCache = { groups, map }
  return map
}

// Base-item implicits the legendary catalog often omits (e.g. a belt base's "+110 Max Life"). Weapon base
// stats (damage/APS/CSR) are excluded — those are granted via the weapon path, not injected here.
const _WEAPON_IMPLICIT_RE = /(Physical Damage|Attack Speed|Critical Strike Rating)\s*$/i
let _baseImplCache: { groups: CraftBaseItemGroup[]; map: Map<string, string[]> } | null = null
function _baseItemImplicits(baseType: string | undefined | null): string[] {
  if (!baseType) return []
  const groups = useReferenceStore.getState().craftBaseItems ?? []
  if (!_baseImplCache || _baseImplCache.groups !== groups) {
    const map = new Map<string, string[]>()
    for (const g of groups) {
      for (const bi of g.base_items) {
        const impls = (bi.implicits ?? []).filter(t => t && !_WEAPON_IMPLICIT_RE.test(t))
        if (impls.length) map.set(bi.name, impls)
      }
    }
    _baseImplCache = { groups, map }
  }
  return _baseImplCache.map.get(baseType) ?? []
}

// Count of distinct weapon classes across equipped weapon slots — drives the auto-set
// `unique_weapon_types` condition (e.g. Bladerunner's "+X% per unique type of weapon equipped").
// Resolves each weapon's base_type name to its class via the catalog; an unknown base counts as
// its own distinct type so it is never silently dropped.
export function countUniqueWeaponTypes(gear: EquippedGearItem[]): number {
  const weapons = gear.filter(i =>
    (itemHasSlot(i, 'weapon1') || itemHasSlot(i, 'weapon2')) && !isShieldItem(i))
  if (weapons.length === 0) return 0
  const classMap = weaponClassMap()
  const classes = new Set<string>()
  for (const w of weapons) {
    const cls = w.base_type ? classMap.get(w.base_type) : undefined
    classes.add(cls ?? `unknown:${w.base_type ?? w.item_id}`)
  }
  return classes.size
}

// Which weapon-class scenarios the equipped gear actually satisfies — drives Config's Equipment-condition
// visibility (show "Holding Two-Handed" only when a 2H is worn, etc.). Reuses the weapon-class catalog map.
export interface WornWeaponFlags { shield: boolean; oneHanded: boolean; twoHanded: boolean; dualWield: boolean }
export function wornWeaponFlags(gear: EquippedGearItem[]): WornWeaponFlags {
  const classMap = weaponClassMap()
  let shield = false, oneHanded = false, twoHanded = false
  for (const w of gear) {
    if (!(itemHasSlot(w, 'weapon1') || itemHasSlot(w, 'weapon2'))) continue
    if (isShieldItem(w)) { shield = true; continue }
    const cls = w.base_type ? classMap.get(w.base_type) : undefined
    if (cls?.startsWith('two_handed')) twoHanded = true
    else if (cls?.startsWith('one_handed')) oneHanded = true
  }
  return { shield, oneHanded, twoHanded, dualWield: isDualWielding(gear) }
}

/**
 * Assemble the `/engine/stats` request payload from current store state.
 * Shared by the background recalc (useBuildCalculation) and the damage-delta hook so both
 * produce an identical payload — the delta hook then applies a hypothetical change on top.
 */
// Remove ONE occurrence of each listed line from `list` (used to price a single pact-spirit node by
// excluding just its effect line(s); one-occurrence removal so duplicate effect text on other nodes stays).
// Matches on the effect text so it works with the {text, source} effect shape.
function _excludeOnce(list: EffectInput[], exclude?: string[]): EffectInput[] {
  if (!exclude || exclude.length === 0) return list
  const remaining = [...exclude]
  return list.filter(eff => {
    const i = remaining.indexOf(eff.text)
    if (i >= 0) { remaining.splice(i, 1); return false }
    return true
  })
}

export function buildEngineStatsPayload(s: BuildState) {
  // Character level is the `level` condition (default 90) — the single source of truth now that the
  // skills-screen level control is gone. Forced into condition_state so per-level scaling, base life/mana,
  // and energy all agree (and the backend's characterLevel seeding never diverges).
  const charLevel = characterLevelFrom(s.conditionState)
  const _traitSkillActive = traitGrantsSkillSlot(s.traitId, s.advancedTraitSelections)
    && (s.traitSkillSupports?.length ?? 0) > 0
  return {
    slots: s.slots,
    slates: s.slates,
    prisms: s.prisms,   // Inverse Image reflected copies → DPS via node_resolver
    // dual_wielding and unique_weapon_types are auto-derived from gear (override any stored value).
    condition_state: {
      ...s.conditionState,
      level: charLevel,
      dual_wielding: isDualWielding(s.gear),
      unique_weapon_types: countUniqueWeaponTypes(s.gear),
    },
    gear: buildGearPayload(s.gear),
    character: buildCharacterContributions(s.gear, charLevel),
    memory_effects: buildMemoryEffects(s.heroMemories),
    spirit_effects: _excludeOnce(buildSpiritEffects(s.pactSpirits, s.allSpirits, s.fates, s.undetermined), s.spiritEffectExclude),
    // Hero trait. trait_id/levels/picks drive the bespoke engine module; trait_effects feeds the status
    // surface + generic (non-bespoke) traits. uptime_mode (Max|Real) selects assume-max vs computed ramp.
    trait_id: s.traitId,
    trait_slot_levels: s.traitSlotLevels,
    // Effective picks = user choices + always-granted guaranteed nodes (enabled tiers). Sent so both bespoke
    // modules and the generic resolver apply guaranteed nodes without persisting them into the saved selections.
    advanced_trait_selections: _effTraitPicks(s),
    trait_effects: buildTraitEffects(s.traitId, s.traitSlotLevels, _effTraitPicks(s),
      useReferenceStore.getState().heroTraits ?? []),
    // Licorice Note: the Empower/Curse the trait prepares (Pungent cross-apply target). null → auto/none.
    licorice_prepared_skill: s.licoricePreparedSkill ?? null,
    // Licorice Note Ingredients: scent-bottle slot → [equipped ingredient names] (flattened from {category: name}).
    elixir_ingredients: Object.fromEntries(
      Object.entries(s.elixirIngredients ?? {}).map(([slot, byCat]) => [slot, Object.values(byCat).filter(Boolean)])),
    uptime_mode: s.uptimeMode,
    main_skill: s.mainSkill ?? null,
    // The trait skill slot (Holy Domain) is injected as a synthetic slot-10 skill ONLY when the trait grants it
    // AND supports are socketed — its supports then resolve through the normal per-slot machinery (slot 10).
    skills: [
      ...s.skills.map(sk => ({
        slot: sk.slot, skill_id: sk.item_id, level: sk.level ?? 1, enabled: sk.enabled !== false,
      })),
      ...(_traitSkillActive ? [{ slot: TRAIT_SKILL_SLOT, skill_id: TRAIT_SKILL_ID, level: 1, enabled: true }] : []),
    ],
    // Every skill slot carries its own supports. Each support is tagged with its host skill's slot so the
    // engine folds it only into that slot's offense pass (add_slotted) — a non-main-slot skill (e.g. the
    // main damage skill parked in slot 2) gets its supports computed too, not just slot 1's.
    attached_supports: [
      ...s.skills.flatMap(sk =>
        (sk.supports ?? []).map(sup => ({
          item_id: sup.item_id,
          skill_type: sup.skill_type,
          rank: sup.rank,
          level: sup.level,
          specific_rolls: sup.specific_rolls,
          specific_roll_tiers: sup.specific_roll_tiers,
          roll_group_choice: sup.roll_group_choice,
          slot: sk.slot,
          enabled: sup.enabled !== false,
        }))),
      ...(_traitSkillActive ? s.traitSkillSupports.map(sup => ({
        item_id: sup.item_id,
        skill_type: sup.skill_type,
        rank: sup.rank,
        level: sup.level,
        specific_rolls: sup.specific_rolls,
        specific_roll_tiers: sup.specific_roll_tiers,
        roll_group_choice: sup.roll_group_choice,
        slot: TRAIT_SKILL_SLOT,
        enabled: sup.enabled !== false,
      })) : []),
    ],
    custom_mods: s.customMods,
    // Editable calc-target ("dummy") stats — percentages; the engine converts to fractions + applies mitigation.
    target_config: s.targetConfig,
  }
}

// An affix the frontend can't turn into a typed contribution is sent to the backend as raw text (drop()).
// Any value RANGE in that text would otherwise collapse to midpoint server-side — silently discarding a
// roll the user picked in the gear customizer. Substitute each range token with its displayed value
// (chosen_values ?? rounded midpoint — the exact default every other affix already uses), so the engine
// receives precisely what the UI shows: the user's roll when set, midpoint only when untweaked. Fixed
// tokens are already concrete and left untouched. This is what makes the (present) range slider on a
// scoped/unresolved affix actually drive the result instead of being silently ignored.
function _materializeAffixText(affix: LegendaryAffix, cust: CustomizedAffix | undefined): string {
  let text = affix.raw_text
  affix.numeric_values?.forEach((nv, i) => {
    if (nv.kind !== 'range' || !nv.raw) return
    const val = cust?.chosen_values[i] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
    const sign = nv.sign === '-' ? '-' : nv.sign === '+' ? '+' : ''
    text = text.replace(nv.raw, `${sign}${val}`)
  })
  return text
}

function _buildItemContributions(
  item: EquippedGearItem, slot: GearSlot | null, unresolved?: string[],
): GearAffixContribution[] {
  const mutationAffix = item.corrosion_type === 'mutation' ? (item.mutation_resolved_affix ?? null) : null
  let affixesToProcess = mutationAffix ? [mutationAffix, ...item.affixes] : item.affixes
  const affixOffset = mutationAffix ? 1 : 0
  // Inject the base ITEM implicit (e.g. a belt base's "+110 Max Life") when the item carries none — the
  // legendary catalog often omits it, so it'd be silently missing. Appended (indices for customizations stay
  // put); only when the item has NO implicit already. NOTE: a legendary's own implicit is stored with
  // affix_kind 'numeric' (e.g. Tide of the Styx's "+1777 Gear Armor"), so `implicit_count` — the number of
  // leading implicit affixes — is the reliable "already has one" signal; checking affix_kind alone misfires and
  // DOUBLES the implicit (a base-implicit copy on top of the item's own).
  const _hasOwnImplicit = (item.implicit_count ?? 0) > 0 || affixesToProcess.some(a => a.affix_kind === 'implicit')
  if (!_hasOwnImplicit) {
    const baseImpls = _baseItemImplicits(item.base_type)
    if (baseImpls.length) {
      affixesToProcess = [...affixesToProcess, ...baseImpls.map(text => ({
        raw_text: text, modifier_id: null, expression: text, condition: null,
        affix_kind: 'implicit' as const, numeric_values: [], affix_type: 'Implicit',
      }))]
    }
  }
  const contributions: GearAffixContribution[] = []
  // Cardinal rule: never silently drop. Any affix the frontend can't turn into a contribution gets
  // its raw text collected here so the backend can resolve it (and report what it still can't).
  const drop = (text: string | null | undefined) => { if (unresolved && text && text.trim()) unresolved.push(text.trim()) }

  affixesToProcess.forEach((affix, affixIdx) => {
    if (affix.affix_kind === 'placeholder') return
    const cust = item.customizations.find(c => c.affix_index === affixIdx - affixOffset)

    // Craft base type implicits arrive as plain text with no resolved stat keys.
    // Parse the three weapon stat patterns directly so they contribute to the engine.
    if (affix.affix_kind === 'implicit') {
      let handled = false
      const physM = affix.raw_text.match(/^([\d.]+)\s*-\s*([\d.]+)\s+Physical Damage$/i)
      if (physM) {
        contributions.push({ stat: 'physical_dmg_gear_flat_min', display_value: parseFloat(physM[1]), unit: '', item_name: item.name, text: affix.raw_text, slot, condition: null })
        contributions.push({ stat: 'physical_dmg_gear_flat_max', display_value: parseFloat(physM[2]), unit: '', item_name: item.name, text: affix.raw_text, slot, condition: null })
        handled = true
      }
      const atkM = affix.raw_text.match(/^([\d.]+)\s+Attack Speed$/i)
      if (atkM) {
        contributions.push({ stat: 'weapon_attack_speed', display_value: parseFloat(atkM[1]), unit: '', item_name: item.name, text: affix.raw_text, slot, condition: null })
        handled = true
      }
      const csrM = affix.raw_text.match(/^([\d.]+)\s+Critical Strike Rating$/i)
      if (csrM) {
        contributions.push({ stat: 'weapon_crit_rating_flat', display_value: parseFloat(csrM[1]), unit: '', item_name: item.name, text: affix.raw_text, slot, condition: null })
        handled = true
      }
      // Armour base defense implicit ("+N gear Energy Shield|Armour|Evasion") — the base item's flat
      // defense, which feeds that item's local gear pool (scaled by its "% gear X" affixes below).
      const defM = affix.raw_text.match(/^\+?([\d.]+)\s+gear\s+(energy shield|armou?r|evasion)$/i)
      if (defM) {
        const key = ({ 'energy shield': 'energy_shield_gear_flat', 'armor': 'armor_gear_flat',
          'armour': 'armor_gear_flat', 'evasion': 'evasion_gear_flat' } as Record<string, string>)[defM[2].toLowerCase()]
        if (key) { contributions.push({ stat: key, display_value: parseFloat(defM[1]), unit: '', item_name: item.name, text: affix.raw_text, slot, condition: null }); handled = true }
      }
      if (!handled) drop(_materializeAffixText(affix, cust))   // e.g. base resistances / life / attributes → resolve backend-side
      return
    }

    const hasKey = affix.stat_key
      || (affix.stat_keys && affix.stat_keys.length > 0)
      || (affix.dual_stat_groups && affix.dual_stat_groups.length > 0)
      || (affix.min_stat_keys && affix.min_stat_keys.length > 0)
    if (!hasKey) { if (affix.affix_kind !== 'tagged') drop(_materializeAffixText(affix, cust)); return }
    const condition = affix.condition_expr ?? null
    if (affix.affix_kind === 'numeric') {
      const rangeIdx = affix.numeric_values.findIndex(v => v.kind === 'range')
      const fixedNv = affix.numeric_values.find(v => v.kind === 'fixed')
      const unit = affix.unit ?? ''

      if (affix.min_stat_keys && affix.max_stat_keys && rangeIdx >= 0) {
        const nv = affix.numeric_values[rangeIdx]
        const minVal = cust?.chosen_values[0] ?? Math.round(nv.min ?? 0)
        const maxVal = cust?.chosen_values[1] ?? Math.round(nv.max ?? 0)
        for (const stat of affix.min_stat_keys) {
          contributions.push({ stat, display_value: minVal, unit, item_name: item.name, text: affix.raw_text, slot, condition })
        }
        for (const stat of affix.max_stat_keys) {
          contributions.push({ stat, display_value: maxVal, unit, item_name: item.name, text: affix.raw_text, slot, condition })
        }
      } else if (affix.dual_stat_groups && affix.dual_stat_groups.length > 0) {
        for (const group of affix.dual_stat_groups) {
          const nv = affix.numeric_values[group.value_index]
          if (!nv) continue
          const groupUnit = group.unit !== undefined ? group.unit : unit
          let val: number
          if (nv.kind === 'range') {
            val = cust?.chosen_values[group.value_index] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
          } else {
            val = (nv.value ?? 0) * (nv.sign === '-' ? -1 : 1)
          }
          for (const stat of group.stat_keys) {
            contributions.push({ stat, display_value: val, unit: groupUnit, item_name: item.name, text: affix.raw_text, slot, condition })
          }
        }
      } else if (affix.stat_keys && affix.stat_keys.length > 0) {
        if (affix.is_range_split && rangeIdx >= 0) {
          const nv = affix.numeric_values[rangeIdx]
          const [minStat, maxStat] = affix.stat_keys
          const minVal = cust?.chosen_values[0] ?? Math.round(nv.min ?? 0)
          const maxVal = cust?.chosen_values[1] ?? Math.round(nv.max ?? 0)
          contributions.push({ stat: minStat, display_value: minVal, unit, item_name: item.name, text: affix.raw_text, slot, condition })
          contributions.push({ stat: maxStat, display_value: maxVal, unit, item_name: item.name, text: affix.raw_text, slot, condition })
        } else {
          let display_value: number | null = null
          if (rangeIdx >= 0) {
            const nv = affix.numeric_values[rangeIdx]
            display_value = cust?.chosen_values[rangeIdx] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
          } else if (fixedNv) {
            display_value = fixedNv.value ?? 0
          }
          if (display_value !== null) {
            for (const stat of affix.stat_keys) {
              contributions.push({ stat, display_value, unit, item_name: item.name, text: affix.raw_text, slot, condition })
            }
          }
        }
      } else if (affix.stat_key) {
        let display_value: number | null = null
        if (rangeIdx >= 0) {
          const nv = affix.numeric_values[rangeIdx]
          display_value = cust?.chosen_values[rangeIdx] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
        } else if (fixedNv) {
          display_value = fixedNv.value ?? 0
        }
        if (display_value !== null) {
          contributions.push({ stat: affix.stat_key, display_value, unit, item_name: item.name, text: affix.raw_text, slot, condition })
        }
      }
    }
  })

  foldLocalGearDefense(contributions, item.name)
  return contributions
}

// Gear defense is LOCAL: each item's flat ES/Armour/Evasion (base implicit + explicit affixes) is
// scaled by that item's "% gear X" affixes, and only the scaled flat feeds the global pool. So we
// pre-apply the local "% gear X" here and emit one folded flat per defense type — the "% gear X" must
// never reach the global increased pool (derive no longer reads *_gear_inc). Global "% increased /
// additional Max X" (max_*_inc / max_*_additional) are separate and still pool globally.
const _GEAR_DEFENSE: { flat: string; inc: string }[] = [
  { flat: 'energy_shield_gear_flat', inc: 'energy_shield_gear_inc' },
  { flat: 'armor_gear_flat',         inc: 'armor_gear_inc' },
  { flat: 'evasion_gear_flat',       inc: 'evasion_gear_inc' },
]
function foldLocalGearDefense(contribs: GearAffixContribution[], itemName: string): void {
  for (const { flat, inc } of _GEAR_DEFENSE) {
    let flatSum = 0, incSum = 0   // incSum is in percent points (e.g. 57 for "+57% gear ES")
    for (const c of contribs) {
      if (c.stat === flat) flatSum += c.display_value
      else if (c.stat === inc) incSum += c.display_value
    }
    // Drop the raw flat + inc rows for this defense type…
    for (let i = contribs.length - 1; i >= 0; i--) {
      if (contribs[i].stat === flat || contribs[i].stat === inc) contribs.splice(i, 1)
    }
    // …and re-emit the locally-scaled flat (base + explicit) × (1 + Σ % gear X).
    if (flatSum > 0) {
      contribs.push({ stat: flat, display_value: flatSum * (1 + incSum / 100), unit: '',
        item_name: itemName, text: `Local gear defense (×${(1 + incSum / 100).toFixed(2)})`, slot: null, condition: null })
    }
  }
}

function _isWeaponSpecificStat(stat: string): boolean {
  // Weapon implicit base stats (attack speed, base damage, flat CSR) and per-weapon gear
  // multipliers must NOT be doubled for same-item dual wield. When the same weapon is in
  // both slots, attacks alternate between identical copies — averaging two identical values
  // equals one, so counting these once is correct.
  // Global affixes (resistance, %dmg_inc, etc.) should stack from both slots.
  // attack_crit_rating_gear is per-weapon (confirmed): it scales that weapon's CSR only.
  // attack_crit_rating_mh is mainhand-only (confirmed): applies to weapon1 slot only.
  return stat.startsWith('weapon_')
    || stat.includes('_gear_')
    || stat === 'attack_crit_rating_mh'
    || stat === 'attack_crit_rating_gear'
    || stat === 'attack_speed_gear'
    || stat === 'attack_speed_mh'
}

// Damage types that can appear as per-weapon flat stats on a weapon item.
// "elemental" is included because elemental_dmg_gear_flat_min/max can appear on weapons
// (currently unprocessed by the offense engine but averaged here for future correctness).
const _WEAPON_DAMAGE_TYPES = [...DAMAGE_TYPES, 'elemental'] as const

// Build per-weapon-effective contributions for two different weapons in weapon1 + weapon2.
// Per the alternating-attack mechanic, attacks alternate between weapons. This means:
//   - Base stats (APS, flat damage, flat CSR) must be AVERAGED across both weapons,
//     and per-weapon gear multipliers (e.g. physical_dmg_gear_inc) must be applied
//     PER WEAPON before averaging to avoid cross-multiplication errors.
//   - Global affixes (resistance, %dmg_inc, etc.) stack from both weapons.
//
// Per-weapon effective CSR formula per weapon slot:
//   W_eff_csr = W_csr_flat × (1 + W_crit_gear/100 + W_crit_mh/100)
// Where attack_crit_rating_mh ONLY applies when the weapon is in weapon1 (mainhand).
// attack_crit_rating_gear is per-weapon (confirmed): scales that weapon's CSR only.
// Both multipliers are pre-applied here and NOT emitted as global stats, preventing
// the engine from applying them a second time.
function _buildDualWieldContributions(w1: EquippedGearItem, w2: EquippedGearItem): GearEngineItem[] {
  const weapons = [w1, w2] as const
  const globalContribs: GearAffixContribution[] = []
  // Per-weapon unresolved affix/implicit texts (e.g. a caster wand's "+40% Spell Damage" implicit) — these
  // are global increased pools, not weapon base stats, so each weapon's stacks (like its typed affixes).
  const unresolvedByWeapon: string[][] = weapons.map(() => [])

  type WeaponAccum = {
    aps:           number
    aps_gear:      number   // attack_speed_gear display_value (e.g. 27 for 27%)
    aps_mh:        number   // attack_speed_mh display_value — only weapon1
    csr_flat:      number
    csr_crit_gear: number   // attack_crit_rating_gear display_value (e.g. 20 for 20%)
    csr_crit_mh:   number   // attack_crit_rating_mh display_value — only weapon1
    dmg_flat_min:  Record<string, number>
    dmg_flat_max:  Record<string, number>
    dmg_gear_inc:  Record<string, number>  // display_value (e.g. 29 for 29%)
  }
  const accums: WeaponAccum[] = weapons.map(() => ({
    aps: 0, aps_gear: 0, aps_mh: 0,
    csr_flat: 0, csr_crit_gear: 0, csr_crit_mh: 0,
    dmg_flat_min: {}, dmg_flat_max: {}, dmg_gear_inc: {},
  }))

  for (let wi = 0; wi < weapons.length; wi++) {
    const weapon    = weapons[wi]
    const slot      = weapon.slot as GearSlot
    const isMainhand = slot === 'weapon1'
    const acc       = accums[wi]

    for (const c of _buildItemContributions(weapon, slot, unresolvedByWeapon[wi])) {
      if (c.stat === 'weapon_attack_speed') {
        acc.aps += c.display_value
      } else if (c.stat === 'attack_speed_gear') {
        // Per-weapon confirmed (same pattern as attack_crit_rating_gear): pre-multiply per weapon
        acc.aps_gear += c.display_value
      } else if (c.stat === 'attack_speed_mh') {
        // Mainhand-only confirmed: only applies when weapon is in weapon1 slot
        if (isMainhand) acc.aps_mh += c.display_value
      } else if (c.stat === 'weapon_crit_rating_flat') {
        acc.csr_flat += c.display_value
      } else if (c.stat === 'attack_crit_rating_gear') {
        // Per-weapon confirmed: each weapon's gear multiplier scales only that weapon's CSR
        acc.csr_crit_gear += c.display_value
      } else if (c.stat === 'attack_crit_rating_mh') {
        // Mainhand-only confirmed: only applies when weapon is in weapon1 slot
        if (isMainhand) acc.csr_crit_mh += c.display_value
        // Offhand weapon's attack_crit_rating_mh is silently discarded — it has no effect
      } else {
        let handled = false
        for (const dtype of _WEAPON_DAMAGE_TYPES) {
          if (c.stat === `${dtype}_dmg_gear_flat_min`) {
            acc.dmg_flat_min[dtype] = (acc.dmg_flat_min[dtype] ?? 0) + c.display_value
            handled = true; break
          } else if (c.stat === `${dtype}_dmg_gear_flat_max`) {
            acc.dmg_flat_max[dtype] = (acc.dmg_flat_max[dtype] ?? 0) + c.display_value
            handled = true; break
          } else if (c.stat === `${dtype}_dmg_gear_inc`) {
            acc.dmg_gear_inc[dtype] = (acc.dmg_gear_inc[dtype] ?? 0) + c.display_value
            handled = true; break
          }
        }
        if (!handled) {
          // Not a recognised per-weapon base/multiplier stat — emit as global (stacks from both).
          // Includes: elemental_resistance, physical_dmg_inc, and other non-weapon-specific affixes.
          globalContribs.push(c)
        }
      }
    }
  }

  const numWeapons = weapons.length
  const avgContribs: GearAffixContribution[] = []

  // APS — per-weapon pre-multiply then emit each weapon's proportional share (effAps/numWeapons),
  // so the breakdown shows each weapon as its own hover-able source (matches CSR + damage below).
  // Formula: eff_aps = aps × (1 + aps_gear/100 + aps_mh/100); shares sum to the averaged total.
  // attack_speed_gear and _mh are NOT emitted as global stats; engine sees (1+0) for that factor.
  for (let wi = 0; wi < numWeapons; wi++) {
    const acc = accums[wi]
    const wName = wi === 0 ? w1.name : w2.name
    const wSlot = wi === 0 ? w1.slot as GearSlot : w2.slot as GearSlot
    const effAps = acc.aps * (1 + (acc.aps_gear + acc.aps_mh) / 100)
    const proportionalAps = effAps / numWeapons
    if (proportionalAps > 0) {
      avgContribs.push({ stat: 'weapon_attack_speed', display_value: proportionalAps, unit: '', item_name: wName, slot: wSlot, condition: null })
    }
  }

  // CSR — per-weapon pre-multiply then average, emitted as separate per-weapon contributions
  // so the source popup shows each weapon independently rather than a merged "W1 / W2" entry.
  // Each weapon's proportional share (effCsr / numWeapons) sums to the correct averaged total.
  for (let wi = 0; wi < numWeapons; wi++) {
    const acc = accums[wi]
    const wName = wi === 0 ? w1.name : w2.name
    const wSlot = wi === 0 ? w1.slot as GearSlot : w2.slot as GearSlot
    const effCsr = acc.csr_flat * (1 + (acc.csr_crit_gear + acc.csr_crit_mh) / 100)
    const proportionalCsr = effCsr / numWeapons
    if (proportionalCsr > 0) {
      avgContribs.push({ stat: 'weapon_crit_rating_flat', display_value: proportionalCsr, unit: '', item_name: wName, slot: wSlot, condition: null })
    }
  }

  // Damage — per-weapon: apply each weapon's gear_inc multiplier, then emit that weapon's proportional
  // share (effective/numWeapons) as its OWN contribution (name + slot), so each weapon shows as a
  // separate, hover-able source instead of a merged "W1 / W2" entry. Shares sum to the averaged total.
  // Formula: effective_min = flat_min × (1 + gear_inc / 100). The pre-multiplied value is emitted as a
  // flat (unit:'') contribution so the engine applies × (1 + 0) — no gear_inc emitted (no double-count).
  for (const dtype of _WEAPON_DAMAGE_TYPES) {
    for (let wi = 0; wi < numWeapons; wi++) {
      const acc = accums[wi]
      const wName = wi === 0 ? w1.name : w2.name
      const wSlot = wi === 0 ? w1.slot as GearSlot : w2.slot as GearSlot
      const multiplier = 1 + (acc.dmg_gear_inc[dtype] ?? 0) / 100
      const minShare = (acc.dmg_flat_min[dtype] ?? 0) * multiplier / numWeapons
      const maxShare = (acc.dmg_flat_max[dtype] ?? 0) * multiplier / numWeapons
      if (minShare > 0) {
        avgContribs.push({ stat: `${dtype}_dmg_gear_flat_min`, display_value: minShare, unit: '', item_name: wName, slot: wSlot, condition: null })
      }
      if (maxShare > 0) {
        avgContribs.push({ stat: `${dtype}_dmg_gear_flat_max`, display_value: maxShare, unit: '', item_name: wName, slot: wSlot, condition: null })
      }
    }
  }

  const result: GearEngineItem[] = []
  if (avgContribs.length > 0) result.push({ contributions: avgContribs })
  if (globalContribs.length > 0) result.push({ contributions: globalContribs })
  // Each weapon's unresolved texts (e.g. wand "+40% Spell Damage" implicit) — backend-resolved, attributed to
  // the weapon, and stacking from both (they're global pools, not averaged weapon base stats).
  for (let wi = 0; wi < weapons.length; wi++) {
    if (unresolvedByWeapon[wi].length > 0) {
      result.push({ contributions: [], item_name: weapons[wi].name, unresolved_texts: unresolvedByWeapon[wi] })
    }
  }
  return result
}

// Bracket-named core-talent grants on a legendary affix: "[Sacrifice] Changes the base effect …".
// Mirrors the backend belt_blend_importer _BRACKET_RE — the bracket name is the granted core talent.
const _BRACKET_RE = /^\s*\[([^\]]+)\]/
function grantedTalentsOf(item: EquippedGearItem): string[] {
  const names: string[] = []
  for (const affix of item.affixes ?? []) {
    const m = _BRACKET_RE.exec(affix.raw_text ?? '')
    if (m) names.push(m[1].trim())
  }
  return names
}

// Tag a gear engine item with its core-talent grants (belt blend + bracket affixes) so the server's
// resolve_core_talents can read them. No-op (returns the item unchanged) when there's nothing to add.
function withCoreTalentGrants(gi: GearEngineItem, item: EquippedGearItem): GearEngineItem {
  const granted = grantedTalentsOf(item)
  const isBelt = Array.isArray(item.slot) ? item.slot.includes('belt') : item.slot === 'belt'
  const beltBlend = isBelt ? (item.beltBlend ?? null) : null
  if (granted.length === 0 && !beltBlend) return gi
  return { ...gi, ...(granted.length ? { granted_talents: granted } : {}), ...(beltBlend ? { belt_blend: beltBlend } : {}) }
}

export function buildGearPayload(gear: EquippedGearItem[]): GearEngineItem[] {
  const result: GearEngineItem[] = []

  // Separate single-string weapon-slot items from all others.
  // Array-slot items (same-item dual wield, e.g. slot: ['weapon1','weapon2']) are NOT
  // single-string weapon slots and go through the standard path below.
  const singleWeaponItems: EquippedGearItem[] = []

  for (const item of gear) {
    if (item.slot === null) continue

    // Only actual WEAPONS enter the weapon-averaging path. A shield in weapon2 is NOT a weapon: including it
    // would make a weapon+shield build average the weapon's base stats (APS/damage/CSR) with the shield (e.g.
    // a 1.5-APS weapon → 1.03), which is wrong. Shields fall through to the standard path so their defense/affix
    // contributions still apply. (Mirrors isDualWielding, which already excludes shields.)
    if (!Array.isArray(item.slot) && (item.slot === 'weapon1' || item.slot === 'weapon2') && !isShieldItem(item)) {
      singleWeaponItems.push(item)
      continue
    }

    // Non-weapon slots and same-item dual-wield (array slot).
    const slots: (GearSlot | null)[] = Array.isArray(item.slot) ? item.slot : [item.slot]

    // First slot: emit all contributions (+ any core-talent grants this item carries).
    const unresolved: string[] = []
    const gi = withCoreTalentGrants({ contributions: _buildItemContributions(item, slots[0], unresolved) }, item)
    // Carry item_name + slot on the unresolved push so backend-resolved affixes (e.g. per-consumed flat
    // damage) attribute to the actual item in the breakdown's Source Name (+ gear tooltip) and to its real
    // slot in the Source column — not a generic "Gear" / "Item".
    result.push(unresolved.length ? { ...gi, item_name: item.name, slot: slots[0] ?? null, unresolved_texts: unresolved } : gi)

    // Additional slots (same-item dual wield): emit ONLY global affixes.
    // Per the dual-wield mechanic, attacks alternate — weapon base stats (APS, base damage,
    // flat CSR, per-weapon gear multipliers) are effectively averaged across both weapons.
    // For identical weapons averaging = same as once, so we skip them on slots 1+.
    for (let i = 1; i < slots.length; i++) {
      const u: string[] = []
      const globalContribs = _buildItemContributions(item, slots[i], u)
        .filter(c => !_isWeaponSpecificStat(c.stat))
      if (globalContribs.length > 0) {
        result.push({ contributions: globalContribs })
      }
      // The 2nd copy's untyped global affixes/implicits (e.g. a wand's "+40% Spell Damage") stack too.
      if (u.length > 0) {
        result.push({ contributions: [], item_name: item.name, unresolved_texts: u })
      }
    }
  }

  if (singleWeaponItems.length >= 2) {
    // Two different weapons in weapon1 + weapon2 — per-weapon effective computation.
    result.push(..._buildDualWieldContributions(singleWeaponItems[0], singleWeaponItems[1]))
  } else {
    // 0 or 1 weapon equipped — normal single-weapon path.
    for (const item of singleWeaponItems) {
      const unresolved: string[] = []
      const gi = withCoreTalentGrants({ contributions: _buildItemContributions(item, item.slot as GearSlot, unresolved) }, item)
      // Carry item_name + slot (see note above) so single-weapon unresolved affixes attribute to the item/slot.
      result.push(unresolved.length ? { ...gi, item_name: item.name, slot: (Array.isArray(item.slot) ? item.slot[0] : item.slot) ?? null, unresolved_texts: unresolved } : gi)
    }
  }

  return result
}
