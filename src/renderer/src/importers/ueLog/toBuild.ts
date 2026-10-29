import type { Build, EquippedGearItem, GearSlot, Graft, LegendaryAffix, LegendaryGearItem } from '../../api/client'
import type { UeLogCharacterPreview, UeLogGearItem } from './parse'

export interface UeLogBuildResult {
  build: Build
  warnings: string[]
}

export interface UeLogCapture {
  fileNumber: number
  modifiedAt: number
  preview: UeLogCharacterPreview
}

export interface UeLogCharacterGroup {
  fileNumber: number
  preview: UeLogCharacterPreview
  loginCount: number
}

/** Group local captures by character name and HeroId, keeping the latest modified capture for import. */
export function groupUeLogCaptures(captures: UeLogCapture[]): UeLogCharacterGroup[] {
  const groups = new Map<string, UeLogCharacterGroup>()
  const ordered = [...captures].sort((a, b) => a.modifiedAt - b.modifiedAt || a.preview.dumpNumber - b.preview.dumpNumber)
  for (const capture of ordered) {
    const name = capture.preview.characterName?.trim().toLocaleLowerCase() ?? ''
    const key = `${name}\u001f${capture.preview.heroId ?? 'unknown'}`
    const previous = groups.get(key)
    groups.set(key, {
      fileNumber: capture.fileNumber,
      preview: capture.preview,
      loginCount: (previous?.loginCount ?? 0) + 1,
    })
  }
  return Array.from(groups.values())
}

const SLOT_BY_LOG_INDEX: Record<number, GearSlot> = {
  1: 'helmet',
  2: 'weapon1',
  3: 'weapon2',
  4: 'chest',
  5: 'amulet',
  6: 'ring1',
  7: 'ring2',
  8: 'belt',
  9: 'gloves',
  10: 'boots',
}

function legendaryAffixes(item: LegendaryGearItem): LegendaryAffix[] {
  return Object.values(item.variants).flatMap(variant => [...variant.implicits, ...variant.explicits])
}

function byModifierId(items: LegendaryGearItem[], id: string): { item: LegendaryGearItem; affix: LegendaryAffix } | null {
  for (const item of items) {
    const affix = legendaryAffixes(item).find(candidate => candidate.modifier_id === id)
    if (affix) return { item, affix }
  }
  return null
}

function rollCustomization(values: number[], affixIndex: number) {
  if (!values.length) return null
  const chosenValues: Record<number, number> = {}
  values.forEach((value, index) => { chosenValues[index] = value })
  return { affix_index: affixIndex, chosen_values: chosenValues, chosen_placeholder_key: null }
}

function toGraftAffix(
  id: string,
  source: string | null,
  graft: Graft,
  legendaryItems: LegendaryGearItem[],
): { affix: LegendaryAffix; sourceItem?: string } | null {
  if (source === '17') {
    const match = byModifierId(legendaryItems, id)
    if (!match) return null
    return { affix: { ...match.affix, affix_type: 'Legendary' }, sourceItem: match.item.name }
  }

  const poolAffix = graft.affixes.find(candidate => candidate.modifier_id === id)
  if (!poolAffix) return null
  const affix: LegendaryAffix = {
    raw_text: poolAffix.raw_text,
    modifier_id: poolAffix.modifier_id ?? id,
    expression: poolAffix.expression,
    condition: poolAffix.condition,
    affix_kind: poolAffix.affix_kind,
    numeric_values: poolAffix.numeric_values,
    affix_type: source === '16' ? 'Ultimate Affix' : poolAffix.affix_type,
    tier: poolAffix.tier,
    stat_key: poolAffix.stat_key,
    stat_keys: poolAffix.stat_keys,
    is_range_split: poolAffix.is_range_split,
    min_stat_keys: poolAffix.min_stat_keys,
    max_stat_keys: poolAffix.max_stat_keys,
    dual_stat_groups: poolAffix.dual_stat_groups,
    unit: poolAffix.unit,
  }
  return { affix }
}

function buildVoraxItem(
  item: UeLogGearItem,
  graft: Graft,
  legendaryItems: LegendaryGearItem[],
  warnings: string[],
): EquippedGearItem {
  const affixes: LegendaryAffix[] = []
  const customizations: NonNullable<Build['gear']>[number]['customizations'] = []
  const positions: number[] = []
  let legendarySource: string | null = null

  for (const baseId of item.baseAffixIds) {
    warnings.push(`${graft.name}: base affix ${baseId} is not in the current Builder catalogs and was left out.`)
  }

  const groups = [
    { rows: item.prefixes, slotOffset: 2 },
    { rows: item.suffixes, slotOffset: 5 },
  ]
  for (const { rows, slotOffset } of groups) {
    rows.forEach((row, index) => {
      if (!row.id) return
      const mapped = toGraftAffix(row.id, row.source, graft, legendaryItems)
      if (!mapped) {
        warnings.push(`${graft.name}: affix ${row.id} could not be mapped and was left out.`)
        return
      }
      if (mapped.sourceItem) legendarySource = mapped.sourceItem
      const affixIndex = affixes.length
      affixes.push(mapped.affix)
      positions.push(slotOffset + index)
      const customization = rollCustomization(row.values, affixIndex)
      if (customization) customizations.push(customization)
    })
  }

  const slot = SLOT_BY_LOG_INDEX[item.equippedSlot ?? -1] ?? null
  if (!slot) warnings.push(`${graft.name}: equipped slot ${item.equippedSlot ?? 'unknown'} was not recognized.`)
  return {
    item_id: graft.item_id,
    name: `${graft.name.replace('Limb: ', '')} (Vorax)`,
    required_level: 0,
    affixes,
    customizations,
    slot,
    is_crafted: true,
    is_vorax: true,
    legendary_source: legendarySource,
    legendary_affix_count: legendarySource ? 1 : 0,
    craft_slot_positions: positions,
  }
}

/** Create a partial but editable Builder build from the Vorax items this catalog can identify. */
export function createUeLogBuild(
  character: UeLogCharacterPreview,
  grafts: Graft[],
  legendaryItems: LegendaryGearItem[],
): UeLogBuildResult {
  const warnings: string[] = []
  const gear: EquippedGearItem[] = []
  const unmappedBaseIds: number[] = []
  for (const item of character.gear) {
    const graft = grafts.find(candidate => candidate.game_id === item.baseId)
    if (!graft) {
      if (item.baseId !== null) unmappedBaseIds.push(item.baseId)
      continue
    }
    gear.push(buildVoraxItem(item, graft, legendaryItems, warnings))
  }

  if (character.gear.length > gear.length) {
    warnings.unshift(`${character.gear.length - gear.length} of ${character.gear.length} equipped items are not mapped yet. The imported build will contain the Vorax items that were mapped.`)
  }
  if (unmappedBaseIds.length > 0) {
    warnings.push(`Unmapped gear base IDs: ${unmappedBaseIds.join(', ')}.`)
  }
  warnings.unshift('Hero, skills, talents, memories, and other character settings are not imported yet.')

  return {
    build: {
      name: `${character.characterName || `Hero ${character.heroId ?? 'unknown'}`} · Level ${character.level ?? 'unknown'}`,
      slots: [],
      gear,
      skills: [],
      characterLevel: character.level ?? 100,
      notes: 'Imported from UE_game.log. Review the import warnings and complete the missing character data.',
    },
    warnings,
  }
}
