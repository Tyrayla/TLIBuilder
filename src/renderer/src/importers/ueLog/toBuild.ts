import { deriveTraitSlotLevels, type Build, type CraftBaseItemGroup, type CraftBaseType, type CreatedHeroMemory, type EquippedGearItem, type EquippedSkill, type EquippedSupportSkill, type GearSlot, type Graft, type HeroMemoryAffix, type HeroTrait, type LegendaryAffix, type LegendaryGearItem, type MemorySlotSelection, type MemoryRarity, type PrismCatalog, type SavedSlateSlot, type SlatePool, type SkillItem, type TowerSequenceEntry, type BeltBlend, type PactSpirit, type SelectedPactSpirit } from '../../api/client'
import { initSlateSlots, LEGENDARY_ORIENTATIONS, NETHER_KING_ORIGIN_OFFSETS } from '../../crosswalk/slateGeometry'
import { BASE_SLATE_SHAPES, SLATE_BOARD_VALID } from '../../utils/slateGeometry'
import { netherKingBrandVariant, netherKingOrientationCells, type NetherKingVariant } from '../../utils/netherKingSlate'

// Owner-confirmed servant identity where the current spirit catalog does not expose a servant game ID.
// The owner's latest log and pact screen identify servantId 18230 as Kitty Express.
const UE_LOG_PACT_SPIRIT_ITEM_OVERRIDES: Record<number, string> = { 18230: 'kitty_express' }

// Career-to-tree pairs verified against talent game-ID prefixes in docs/LOG_IMPORT_INVESTIGATION.md (F27).
export const UE_LOG_CAREER_TREE_NAMES: Record<number, string> = {
  1: 'God of Might', 12: 'Onslaughter', 4: 'God of War', 42: 'Ronin', 62: 'Steel Vanguard', 54: 'Lich',
}
const UE_LOG_CAREER_GAME_ID_PREFIXES: Record<number, string> = {
  1: '10', 12: '12', 4: '40', 42: '42', 62: '62', 54: '54',
}
// F27: the first two digits of a talent game_id are the career/tree prefix.
// These mappings come from the exact TLIDB talent_id join recorded in the investigation.
export const UE_LOG_GAME_ID_TREE_NAMES: Record<string, string> = {
  '10': 'God of Might', '11': 'The Brave', '12': 'Onslaughter', '13': 'Warlord', '14': 'Warrior',
  '20': 'Goddess of Hunting', '21': 'Marksman', '22': 'Bladerunner', '23': 'Druid', '24': 'Assassin',
  '30': 'Goddess of Knowledge', '31': 'Magister', '32': 'Arcanist', '33': 'Elementalist', '34': 'Prophet',
  '40': 'God of War', '41': 'Shadowdancer', '42': 'Ronin', '43': 'Ranger', '44': 'Sentinel',
  '50': 'Goddess of Deception', '51': 'Shadowmaster', '52': 'Psychic', '53': 'Warlock', '54': 'Lich',
  '60': 'God of Machines', '61': 'Machinist', '62': 'Steel Vanguard', '63': 'Alchemist', '64': 'Artisan',
}
// TLIDB's Nether King's Divinity item records expose one internal ID per variant.
const NETHER_KING_VARIANT_BY_BASE_ID: Record<number, NetherKingVariant> = {
  394004: 'judgment', 394005: 'contamination', 394006: 'banishment',
}

function loggedTalentCoordinates(gameId: string): { column: number; row: number } | null {
  const match = /^(\d{2})(\d{2})(\d{2})/.exec(gameId)
  if (!match) return null
  const encodedY = Number(match[2]), encodedX = Number(match[3])
  if (encodedX < 1 || encodedY < 1) return null
  return { column: encodedY - 1, row: encodedX - 1 }
}
import type { UeLogCharacterPreview, UeLogGearItem, UeLogMemory, UeLogPactContract, UeLogSkillItem, UeLogSlate } from './parse'

export interface UeLogBuildResult {
  build: Build
  warnings: string[]
}

export interface UeLogReferenceCatalogs {
  memories?: {
    base_stats: HeroMemoryAffix[]
    fixed_affixes: HeroMemoryAffix[]
    random_affixes: HeroMemoryAffix[]
    log_base_stats?: { log_modifier_id: string; source: string; stat_name: string }[]
    log_affixes?: { log_modifier_id: string; source: string; group: 'base_stats' | 'fixed_affixes' | 'random_affixes'; affix_uuid: string }[]
  } | null
  traits?: HeroTrait[] | null
  revivalAffixes?: HeroMemoryAffix[] | null
  etherealPrisms?: PrismCatalog | null
  slatePool?: SlatePool | null
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

export function describeUeLogCaptureMerge(loginCount: number): string {
  return `This character has ${loginCount} login captures. The latest complete entry provides the slate board; if the slate section is truncated, the earlier slate board is kept. Gear, skills, memories, contracts, and scent bottle slots merge across entries, with later entries replacing earlier slots. Talent allocations and servant inventory are combined; later core talent choices replace earlier choices for the same tree.`
}

function hasTruncatedSection(preview: UeLogCharacterPreview, path: string): boolean {
  return preview.truncatedSections.some(section => section.replace(/^[| ]+/, '').startsWith(`+${path}+`))
}

/** Group local captures by character name and HeroId, keeping the latest modified capture for import. */
export function groupUeLogCaptures(captures: UeLogCapture[]): UeLogCharacterGroup[] {
  const groups = new Map<string, UeLogCharacterGroup>()
  const ordered = [...captures].sort((a, b) => a.modifiedAt - b.modifiedAt || a.preview.dumpNumber - b.preview.dumpNumber)
  for (const capture of ordered) {
    const name = capture.preview.characterName?.trim().toLocaleLowerCase() ?? ''
    const key = `${name}\u001f${capture.preview.heroId ?? 'unknown'}`
    const previous = groups.get(key)
    const gearBySlot = new Map<string, UeLogGearItem>()
    const rememberGear = (item: UeLogGearItem, index: number) => {
      const itemKey = item.equippedSlot === null
        ? `unknown:${item.baseId ?? 'unknown'}:${index}`
        : `slot:${item.equippedSlot}`
      gearBySlot.set(itemKey, item)
    }
    for (const [index, item] of (previous?.preview.gear ?? []).entries()) rememberGear(item, index)
    for (const [index, item] of capture.preview.gear.entries()) rememberGear(item, index)
    const skillsBySlot = new Map<number, UeLogSkillItem>()
    for (const skill of previous?.preview.skills ?? []) skillsBySlot.set(skill.logIndex, skill)
    for (const skill of capture.preview.skills) skillsBySlot.set(skill.logIndex, skill)
    const servantIds = new Set([
      ...(previous?.preview.servantIds ?? []),
      ...(capture.preview.servantIds ?? []),
    ])
    const truncatedSections = new Set([
      ...(previous?.preview.truncatedSections ?? []),
      ...capture.preview.truncatedSections,
    ])
    const slateSectionTruncated = hasTruncatedSection(capture.preview, 'bag+dressingTalentBlocks')
    const talentSectionTruncated = hasTruncatedSection(capture.preview, 'geniusInfos')
    const memoriesBySlot = new Map<number, UeLogMemory>()
    for (const memory of previous?.preview.memories ?? []) if (memory.slot !== null) memoriesBySlot.set(memory.slot, memory)
    for (const memory of capture.preview.memories ?? []) if (memory.slot !== null) memoriesBySlot.set(memory.slot, memory)
    const contractsByArea = new Map<number, UeLogPactContract>()
    for (const contract of previous?.preview.pactContracts ?? []) contractsByArea.set(contract.areaId, contract)
    for (const contract of capture.preview.pactContracts ?? []) {
      const earlier = contractsByArea.get(contract.areaId)
      contractsByArea.set(contract.areaId, {
        ...contract,
        rank: contract.rank ?? (earlier?.servantId === contract.servantId ? earlier.rank : null),
      })
    }
    const ingredientsBySlot = new Map<string, NonNullable<UeLogCharacterPreview['ingredientChoices']>[number]>()
    for (const choice of previous?.preview.ingredientChoices ?? []) ingredientsBySlot.set(`${choice.bottleSlot}:${choice.materialSlot}`, choice)
    for (const choice of capture.preview.ingredientChoices ?? []) ingredientsBySlot.set(`${choice.bottleSlot}:${choice.materialSlot}`, choice)
    const treesByCareer = new Map<number | null, NonNullable<UeLogCharacterPreview['talentTrees']>[number]>()
    for (const talentTree of [...(previous?.preview.talentTrees ?? []), ...(capture.preview.talentTrees ?? [])]) {
      const earlier = treesByCareer.get(talentTree.careerId)
      treesByCareer.set(talentTree.careerId, {
        ...talentTree,
        allocations: [...new Map([...(earlier?.allocations ?? []), ...talentTree.allocations].map(row => [row.id, row])).values()],
        ...(talentTree.coreTalentSelections !== undefined
          ? { coreTalentSelections: talentSectionTruncated
            ? [...new Set([...(earlier?.coreTalentSelections ?? []), ...talentTree.coreTalentSelections])]
            : talentTree.coreTalentSelections }
          : earlier?.coreTalentSelections !== undefined ? { coreTalentSelections: earlier.coreTalentSelections } : {}),
        // A complete later tree without prismInfo means the prism was removed. Truncation
        // inside geniusInfos makes absence inconclusive for this prism.
        prism: talentTree.prism ?? (talentSectionTruncated ? earlier?.prism : undefined),
      })
    }
    groups.set(key, {
      fileNumber: capture.fileNumber,
      preview: {
        ...capture.preview,
        ...(capture.preview.slates !== undefined || previous?.preview.slates !== undefined
          ? { slates: slateSectionTruncated && previous?.preview.slates !== undefined
            ? previous.preview.slates
            : capture.preview.slates ?? previous?.preview.slates }
          : {}),
        gear: [...gearBySlot.values()].sort((a, b) => (a.equippedSlot ?? Number.MAX_SAFE_INTEGER) - (b.equippedSlot ?? Number.MAX_SAFE_INTEGER)),
        skills: [...skillsBySlot.values()].sort((a, b) => a.logIndex - b.logIndex),
        ...(treesByCareer.size ? { talentTrees: [...treesByCareer.values()] } : {}),
        followServantId: capture.preview.followServantId ?? previous?.preview.followServantId ?? null,
        servantIds: [...servantIds],
        ...(memoriesBySlot.size ? { memories: [...memoriesBySlot.values()].sort((a, b) => (a.slot ?? 0) - (b.slot ?? 0)) } : {}),
        ...(capture.preview.baseMemory ?? previous?.preview.baseMemory
          ? { baseMemory: capture.preview.baseMemory ?? previous?.preview.baseMemory }
          : {}),
        ...(contractsByArea.size ? { pactContracts: [...contractsByArea.values()].sort((a, b) => a.areaId - b.areaId) } : {}),
        ...(ingredientsBySlot.size ? { ingredientChoices: [...ingredientsBySlot.values()] } : {}),
        ...(capture.preview.activeTraitIds ? { activeTraitIds: capture.preview.activeTraitIds } : previous?.preview.activeTraitIds ? { activeTraitIds: previous.preview.activeTraitIds } : {}),
        truncatedSections: [...truncatedSections],
      },
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
  return [
    ...Object.values(item.variants).flatMap(variant => [...variant.implicits, ...variant.explicits]),
    ...Object.values(item.random_affixes ?? {}).flatMap(groups => groups.flatMap(group => group.options)),
  ]
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

  const poolAffix = [...graft.base_affixes, ...graft.affixes].find(candidate => candidate.modifier_id === id)
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

function toCraftAffix(id: string, craftTypes: CraftBaseType[]): LegendaryAffix | null {
  const found = craftTypes.flatMap(type => type.affixes).find(candidate => candidate.modifier_id === id)
  if (!found) return null
  return {
    raw_text: found.raw_text,
    modifier_id: found.modifier_id ?? id,
    expression: found.expression,
    condition: found.condition,
    affix_kind: found.affix_kind,
    numeric_values: found.numeric_values,
    affix_type: found.affix_type,
    tier: found.tier,
    stat_key: found.stat_key,
    stat_keys: found.stat_keys,
    is_range_split: found.is_range_split,
    min_stat_keys: found.min_stat_keys,
    max_stat_keys: found.max_stat_keys,
    dual_stat_groups: found.dual_stat_groups,
    unit: found.unit,
  }
}

function itemSlot(item: UeLogGearItem, warnings: string[]): GearSlot | null {
  const slot = SLOT_BY_LOG_INDEX[item.equippedSlot ?? -1] ?? null
  if (!slot) warnings.push('An equipped gear item has an unrecognized slot and was skipped.')
  return slot
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
}

function warnUnsupportedLogAffixes(item: UeLogGearItem, name: string, warnings: string[], beltBlends: BeltBlend[] = []) {
  for (const id of item.enchantAffixes.flatMap(row => row.id ? [row.id] : [])) {
    if (item.equippedSlot === 8 && beltBlends.some(blend => blend.modifier_id === id)) continue
    warnings.push(`${name}: an enchant effect is missing from the current Builder data and was left out.`)
  }
}

function loggedBeltBlend(item: UeLogGearItem, beltBlends: BeltBlend[]): string | undefined {
  if (item.equippedSlot !== 8) return undefined
  const ids = item.enchantAffixes.flatMap(row => row.id ? [row.id] : [])
  return beltBlends.find(blend => blend.modifier_id && ids.includes(blend.modifier_id))?.talent_id
}

function mapTowerSequence(
  item: UeLogGearItem,
  equipped: EquippedGearItem,
  sequences: TowerSequenceEntry[],
  warnings: string[],
): EquippedGearItem {
  const rows = item.chipAffixes.filter(row => row.id)
  if (!rows.length) return equipped
  if (rows.length > 1) {
    warnings.push(`${equipped.name}: found ${rows.length} chip affixes; only one Tower Sequence can be represented.`)
  }
  const row = rows[0]
  const sequence = sequences.find(candidate => candidate.modifier_id === row.id || candidate.log_modifier_ids?.includes(row.id!))
  if (!sequence) {
    warnings.push(`${equipped.name}: its Tower Sequence chip is missing from the current Builder data and was left out.`)
    return equipped
  }
  return { ...equipped, towerSequence: sequence.affix }
}

function buildVoraxItem(
  item: UeLogGearItem,
  graft: Graft,
  legendaryItems: LegendaryGearItem[],
  warnings: string[],
  beltBlends: BeltBlend[],
): EquippedGearItem {
  const affixes: LegendaryAffix[] = []
  const customizations: NonNullable<Build['gear']>[number]['customizations'] = []
  const positions: number[] = []
  let legendarySource: string | null = null

  for (const id of item.baseAttrAffixIds) {
    const mapped = toGraftAffix(id, null, graft, legendaryItems)
    if (!mapped) {
      warnings.push(`${graft.name}: a base attribute effect is missing from the current Builder data and was left out.`)
      continue
    }
    affixes.push({ ...mapped.affix, affix_kind: 'implicit', affix_type: 'Base' })
  }
  for (const id of item.baseAffixIds) {
    const mapped = toGraftAffix(id, null, graft, legendaryItems)
    if (!mapped) {
      warnings.push(`${graft.name}: a base affix is missing from the current Builder data and was left out.`)
      continue
    }
    affixes.push(mapped.affix)
  }
  warnUnsupportedLogAffixes(item, graft.name, warnings, beltBlends)

  const groups = [
    { rows: item.prefixes, slotOffset: 2 },
    { rows: item.suffixes, slotOffset: 5 },
  ]
  for (const { rows, slotOffset } of groups) {
    rows.forEach((row, index) => {
      if (!row.id) return
      const mapped = toGraftAffix(row.id, row.source, graft, legendaryItems)
      if (!mapped) {
        warnings.push(`${graft.name}: an affix is missing from the current Builder data and was left out.`)
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

  const slot = itemSlot(item, warnings)
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
    implicit_count: affixes.filter(affix => affix.affix_kind === 'implicit').length,
    craft_slot_positions: positions,
    ...(loggedBeltBlend(item, beltBlends) ? { beltBlend: loggedBeltBlend(item, beltBlends) } : {}),
  }
}

function findCraftBase(baseId: number | null, groups: CraftBaseItemGroup[]) {
  if (baseId === null) return null
  for (const group of groups) {
    const item = group.base_items.find(candidate => candidate.game_id === baseId)
    if (item) return { group, item }
  }
  return null
}

function buildCraftedItem(
  item: UeLogGearItem,
  base: CraftBaseItemGroup['base_items'][number],
  craftTypes: CraftBaseType[],
  legendaryItems: LegendaryGearItem[],
  warnings: string[],
  beltBlends: BeltBlend[],
): EquippedGearItem {
  const name = base.name
  const affixes: LegendaryAffix[] = []
  const customizations: NonNullable<Build['gear']>[number]['customizations'] = []
  const positions: number[] = []
  let legendarySource: string | null = null
  const implicitIds = base.implicit_modifier_ids ?? []
  const requestedImplicitIds = item.baseAttrAffixIds.length ? item.baseAttrAffixIds : implicitIds

  for (const id of requestedImplicitIds) {
    const index = implicitIds.indexOf(id)
    const text = index >= 0 ? base.implicits[index] : null
    if (index < 0 || !text) {
      warnings.push(`${name}: a base attribute effect is missing from the current Builder data and was left out.`)
      continue
    }
    affixes.push({
      raw_text: text,
      modifier_id: id,
      expression: text,
      condition: null,
      affix_kind: 'implicit',
      numeric_values: [],
      affix_type: 'Base',
    })
  }

  for (const [index, id] of item.baseAffixIds.entries()) {
    const mapped = toCraftAffix(id, craftTypes)
    if (!mapped) {
      warnings.push(`${name}: a base affix is missing from the current Builder data and was left out.`)
      continue
    }
    positions.push(index)
    affixes.push(mapped)
  }

  const addExplicitRows = (rows: UeLogGearItem['prefixes'], slotOffset: number) => {
    rows.forEach((row, index) => {
      if (!row.id) return
      const uniqueMatch = row.source === '17' ? byModifierId(legendaryItems, row.id) : null
      const mapped = uniqueMatch
        ? { affix: { ...uniqueMatch.affix, affix_type: 'Legendary' }, sourceItem: uniqueMatch.item.name }
        : null
      const affix = mapped?.affix ?? toCraftAffix(row.id, craftTypes)
      if (!affix) {
        warnings.push(`${name}: an affix is missing from the current Builder data and was left out.`)
        return
      }
      if (mapped?.sourceItem) legendarySource = mapped.sourceItem
      positions.push(slotOffset + index)
      const affixIndex = affixes.length
      affixes.push(affix)
      const customization = rollCustomization(row.values, affixIndex)
      if (customization) customizations.push(customization)
    })
  }

  addExplicitRows(item.prefixes, 2)
  addExplicitRows(item.suffixes, 5)
  warnUnsupportedLogAffixes(item, name, warnings, beltBlends)
  if (item.corroded) warnings.push(`${name}: corruption state is not represented for ordinary crafted gear.`)

  return {
    item_id: slug(name),
    name: `${name} (Crafted)`,
    base_type: base.name,
    required_level: base.required_level,
    affixes,
    customizations,
    slot: itemSlot(item, warnings),
    is_crafted: true,
    implicit_count: affixes.filter(affix => affix.affix_kind === 'implicit').length,
    legendary_source: legendarySource,
    legendary_affix_count: legendarySource ? 1 : 0,
    craft_slot_positions: positions,
    ...(loggedBeltBlend(item, beltBlends) ? { beltBlend: loggedBeltBlend(item, beltBlends) } : {}),
  }
}

function buildUniqueItem(
  item: UeLogGearItem,
  unique: LegendaryGearItem,
  craftBaseItems: CraftBaseItemGroup[],
  craftTypes: CraftBaseType[],
  legendaryItems: LegendaryGearItem[],
  warnings: string[],
  beltBlends: BeltBlend[],
): EquippedGearItem {
  const variant = unique.variants.base ?? Object.values(unique.variants)[0]
  const affixes: LegendaryAffix[] = [...variant.implicits, ...variant.explicits]
  const customizations: NonNullable<Build['gear']>[number]['customizations'] = []
  const positions: number[] = []
  const corrodedExplicitIndices = new Set<number>()
  const selectedRandomAffixes: Record<number, string> = {}
  let legendarySource: string | null = null

  const findUniqueExplicit = (id: string): { index: number; corroded: boolean; random: boolean } | null => {
    const base = unique.variants.base?.explicits ?? []
    const corroded = unique.variants.corroded?.explicits ?? []
    const baseIndex = base.findIndex(affix => affix.modifier_id === id)
    if (baseIndex >= 0) return { index: baseIndex, corroded: false, random: false }
    const corrodedIndex = corroded.findIndex(affix => affix.modifier_id === id)
    if (corrodedIndex >= 0 && base[corrodedIndex]) return { index: corrodedIndex, corroded: true, random: false }

    for (const [variantKey, isCorroded] of [['base', false], ['corroded', true]] as const) {
      const groups = unique.random_affixes?.[variantKey] ?? []
      const placeholders = (isCorroded ? corroded : base)
        .flatMap((affix, index) => affix.affix_kind === 'placeholder' ? [index] : [])
      for (const [groupIndex, group] of groups.entries()) {
        if (group.options.some(option => option.modifier_id === id) && placeholders[groupIndex] !== undefined
          && base[placeholders[groupIndex]]) {
          return { index: placeholders[groupIndex], corroded: isCorroded, random: true }
        }
      }
    }
    return null
  }

  const applyRolls = (rows: UeLogGearItem['prefixes'], slotOffset: number) => {
    rows.forEach((row, index) => {
      if (!row.id) return
      const explicit = findUniqueExplicit(row.id)
      if (explicit) {
        if (explicit.corroded) corrodedExplicitIndices.add(explicit.index)
        if (explicit.random) selectedRandomAffixes[explicit.index] = row.id
        const customization = rollCustomization(row.values, variant.implicits.length + explicit.index)
        if (customization) customizations.push(customization)
        positions.push(slotOffset + index)
        return
      }
      let affixIndex = -1
      const sameUnique = legendaryAffixes(unique).find(candidate => candidate.modifier_id === row.id)
      if (sameUnique) {
        affixIndex = affixes.length
        affixes.push(row.source === '17' ? { ...sameUnique, affix_type: 'Legendary' } : sameUnique)
      }
      if (row.source === '17') {
        const mapped = byModifierId(legendaryItems, row.id)
        if (mapped && affixIndex < 0) {
          affixIndex = affixes.length
          affixes.push({ ...mapped.affix, affix_type: 'Legendary' })
          legendarySource = mapped.item.name
        }
      }
      if (affixIndex < 0) {
        const mapped = toCraftAffix(row.id, craftTypes)
        if (mapped) {
          affixIndex = affixes.length
          affixes.push(mapped)
        }
      }
      if (affixIndex < 0) {
        warnings.push(`${unique.name}: an affix is missing from the current Builder data and was left out.`)
        return
      }
      positions.push(slotOffset + index)
      const customization = rollCustomization(row.values, affixIndex)
      if (customization) customizations.push(customization)
    })
  }

  applyRolls(item.prefixes, 2)
  applyRolls(item.suffixes, 5)
  for (const id of [...item.baseAttrAffixIds, ...item.baseAffixIds]) {
    if (affixes.some(affix => affix.modifier_id === id)) continue
    const foundBase = findCraftBase(item.baseId, craftBaseItems)?.item
    const implicitIndex = foundBase?.implicit_modifier_ids?.indexOf(id) ?? -1
    const implicitText = implicitIndex >= 0 ? foundBase?.implicits[implicitIndex] : null
    if (implicitText) affixes.push({ raw_text: implicitText, modifier_id: id, expression: implicitText, condition: null, affix_kind: 'implicit', numeric_values: [], affix_type: 'Base' })
    else {
      const mapped = toCraftAffix(id, craftTypes)
      if (mapped) affixes.push(mapped)
      else warnings.push(`${unique.name}: a base affix is missing from the current Builder data.`)
    }
  }
  if (item.corroded && corrodedExplicitIndices.size === 0) {
    warnings.push(`${unique.name}: the log marks this item as corroded, but no corroded catalog affix was identified.`)
  }
  warnUnsupportedLogAffixes(item, unique.name, warnings, beltBlends)

  return {
    item_id: unique.item_id,
    name: unique.name,
    base_type: unique.base_type,
    required_level: unique.required_level,
    affixes,
    customizations,
    slot: itemSlot(item, warnings),
    implicit_count: affixes.filter(affix => affix.affix_kind === 'implicit').length,
    legendary_source: legendarySource,
    legendary_affix_count: legendarySource ? 1 : 0,
    craft_slot_positions: positions,
    ...(corrodedExplicitIndices.size ? {
      corrosion_type: 'desecration' as const,
      corroded_explicit_indices: [...corrodedExplicitIndices].sort((a, b) => a - b),
    } : {}),
    ...(Object.keys(selectedRandomAffixes).length ? { selected_random_affixes: selectedRandomAffixes } : {}),
    ...(loggedBeltBlend(item, beltBlends) ? { beltBlend: loggedBeltBlend(item, beltBlends) } : {}),
  }
}

const PASSIVE_SKILL_INDEXES = [1001, 1007, 1013, 1019]
const SUPPORT_SKILL_TYPES = new Set(['support_skill', 'noble_support_skill', 'magnificent_support_skill', 'activation_medium_skill'])
const RANKED_SUPPORT_TYPES = new Set(['noble_support_skill', 'magnificent_support_skill'])

function skillPosition(logIndex: number): { rootIndex: number; buildSlot: number; supportIndex: number | null } | null {
  if (logIndex >= 1 && logIndex <= 5) return { rootIndex: logIndex, buildSlot: logIndex, supportIndex: null }
  if (logIndex >= 101 && logIndex <= 505) {
    const rootIndex = Math.floor(logIndex / 100)
    const supportIndex = logIndex % 100
    if (rootIndex >= 1 && rootIndex <= 5 && supportIndex >= 1 && supportIndex <= 5) {
      return { rootIndex, buildSlot: rootIndex, supportIndex }
    }
  }
  for (let index = 0; index < PASSIVE_SKILL_INDEXES.length; index++) {
    const rootIndex = PASSIVE_SKILL_INDEXES[index]
    const nextRoot = PASSIVE_SKILL_INDEXES[index + 1] ?? rootIndex + 6
    if (logIndex >= rootIndex && logIndex < nextRoot) {
      return {
        rootIndex,
        buildSlot: 6 + index,
        supportIndex: logIndex === rootIndex ? null : logIndex - rootIndex,
      }
    }
  }
  return null
}

function buildLoggedSkills(
  loggedSkills: UeLogSkillItem[],
  catalog: SkillItem[],
  warnings: string[],
): EquippedSkill[] {
  const mapped = loggedSkills.flatMap(row => {
    const position = skillPosition(row.logIndex)
    if (!position) {
      warnings.push('An equipped skill could not be placed in a Builder skill slot and was skipped.')
      return []
    }
    const item = catalog.find(skill => skill.game_id === row.baseId && skill.game_id !== 0)
    if (!item) {
      warnings.push('An equipped skill is missing from the current Builder data and was skipped.')
      return []
    }
    const isSupport = SUPPORT_SKILL_TYPES.has(item.skill_type ?? '') || item.skill_tags.includes('Support')
    return [{ row, position, item, isSupport }]
  })

  const roots = new Map<number, EquippedSkill>()
  const passiveSlots = new Map(
    [...new Set(mapped
      .filter(({ position, isSupport }) => position.supportIndex === null && !isSupport && position.rootIndex >= 1001)
      .map(({ position }) => position.rootIndex))]
      .sort((a, b) => a - b)
      .map((rootIndex, index) => [rootIndex, 6 + index]),
  )
  for (const { row, position, item, isSupport } of mapped) {
    if (position.supportIndex !== null || isSupport) continue
    const level = row.level ?? 20
    if (row.level === null) warnings.push(`${item.name}: skill level was missing from the selected logs; Builder default level ${level} was used.`)
    roots.set(position.rootIndex, {
      slot: passiveSlots.get(position.rootIndex) ?? position.buildSlot,
      item_id: item.item_id,
      name: item.name,
      level,
      skill_tags: item.skill_tags,
      description_lines: item.description_lines,
      supports: [],
    })
  }

  for (const { row, position, item, isSupport } of mapped) {
    if (position.supportIndex === null && !isSupport) continue
    if (position.supportIndex === null) {
      warnings.push(`${item.name}: the log does not identify a support socket for this item, so it was not attached.`)
      continue
    }
    const root = roots.get(position.rootIndex)
    if (!root) {
      warnings.push(`${item.name}: its active skill is missing from the selected login captures, so this support was not attached.`)
      continue
    }
    const skillType = item.skill_type ?? 'support_skill'
    const level = row.level ?? Math.min(20, item.max_level ?? 20)
    if (row.level === null) warnings.push(`${item.name}: support level was missing from the selected logs; Builder default level ${level} was used.`)
    root.supports.push({
      support_index: position.supportIndex,
      item_id: item.item_id,
      name: item.name,
      skill_type: skillType,
      level,
      ...(RANKED_SUPPORT_TYPES.has(skillType) ? { rank: 1 } : {}),
      skill_tags: item.skill_tags,
      description_lines: item.description_lines,
    } satisfies EquippedSupportSkill)
    if (row.prefixes.length) warnings.push(`${item.name}: one or more logged support rolls could not be matched; Builder defaults were used.`)
    if (RANKED_SUPPORT_TYPES.has(skillType) && row.prefixes.length === 0) {
      warnings.push(`${item.name}: support rank is not present in the log; Builder rank 1 was used.`)
    }
  }

  return [...roots.values()].map(skill => ({
    ...skill,
    supports: skill.supports.sort((a, b) => a.support_index - b.support_index),
  })).sort((a, b) => a.slot - b.slot)
}

const MEMORY_TYPE_BY_GAME_ID: Record<number, CreatedHeroMemory['memoryType']> = {
  71001: 'origin', 71002: 'discipline', 71003: 'progress',
}
const MEMORY_SOURCE_BY_TYPE: Record<CreatedHeroMemory['memoryType'], string> = {
  origin: 'Memory of Origin', discipline: 'Memory of Discipline', progress: 'Memory of Progress',
}
const MEMORY_RARITY_BY_LOG_VALUE: Record<number, MemoryRarity> = {
  1: 'normal', 2: 'magic', 3: 'rare', 4: 'epic', 5: 'ultimate',
}
const MEMORY_TYPE_LABEL: Record<CreatedHeroMemory['memoryType'], string> = {
  origin: 'Origin', discipline: 'Discipline', progress: 'Progress',
}
const MEMORY_RARITY_LABEL: Record<MemoryRarity, string> = {
  normal: 'Normal', magic: 'Magic', rare: 'Rare', epic: 'Epic', ultimate: 'Ultimate',
}

function loggedMemorySelection(
  row: UeLogMemory['fixedAffixes'][number], pool: HeroMemoryAffix[], source: string,
  group: 'base_stats' | 'fixed_affixes' | 'random_affixes', logAffixes: NonNullable<UeLogReferenceCatalogs['memories']>['log_affixes'],
  warnings: string[], label: string,
): MemorySlotSelection | null {
  const logAffix = logAffixes?.find(entry => entry.log_modifier_id === row.id && entry.source === source && entry.group === group)
  const match = pool.find(candidate => candidate.source === source && (
    (candidate as HeroMemoryAffix & { modifier_id?: string | null }).modifier_id === row.id
    || (!!logAffix && candidate.uuid === logAffix.affix_uuid)
  ))
  if (!match) {
    warnings.push(`${label}: one logged memory affix could not be matched to TLIDB and was left out.`)
    return null
  }
  const modifier = match.modifier
  const ranges = modifier.match(/\(-?\d+(?:\.\d+)?[–-]-?\d+(?:\.\d+)?\)/g)?.length ?? 0
  const selection: MemorySlotSelection = {
    modifier,
    tier: match.tier ?? 0,
    ...(match.tier_known === false ? { tierKnown: false } : {}),
    rolledValue: ranges === 1 || (ranges === 0 && row.values.length === 1) ? row.values[0] ?? null : null,
    ...(ranges > 1 ? { rolledValues: row.values } : {}),
  }
  return selection
}

function loggedMemoryBaseStatSelection(
  row: UeLogMemory['baseAttrAffixes'][number], catalog: NonNullable<UeLogReferenceCatalogs['memories']>,
  source: string, logAffixes: NonNullable<UeLogReferenceCatalogs['memories']>['log_affixes'], warnings: string[], label: string,
): MemorySlotSelection | null {
  const crosswalk = catalog.log_base_stats?.find(entry => entry.log_modifier_id === row.id && entry.source === source)
  if (!crosswalk) return loggedMemorySelection(row, catalog.base_stats, source, 'base_stats', logAffixes, warnings, label)

  const candidates = catalog.base_stats.filter(entry => entry.source === source
    && entry.modifier.replace(/^\s*[+-]?\d+(?:\.\d+)?\s*%?\s*/, '').trim() === crosswalk.stat_name)
  if (!candidates.length) {
    warnings.push(`${label}: TLIDB has no ${crosswalk.stat_name} option for this memory type.`)
    return null
  }
  const loggedValue = row.values[0]
  const closest = loggedValue === undefined
    ? candidates[0]
    : candidates.reduce((best, candidate) => {
      const value = Number(candidate.modifier.match(/^\s*[+-]?\s*(\d+(?:\.\d+)?)/)?.[1])
      const bestValue = Number(best.modifier.match(/^\s*[+-]?\s*(\d+(?:\.\d+)?)/)?.[1])
      return Math.abs(value - loggedValue) < Math.abs(bestValue - loggedValue) ? candidate : best
    })
  const modifier = closest.modifier.replace(/^(\s*[+-]?\s*)\d+(?:\.\d+)?/, (_match, sign: string) => `${sign || '+'}${loggedValue ?? ''}`)
  return { modifier, tier: closest.tier ?? 0, rolledValue: null }
}

function loggedMemory(
  row: UeLogMemory, catalog: UeLogReferenceCatalogs['memories'], warnings: string[], label: string,
): CreatedHeroMemory | null {
  if (row.baseId === null) return null
  const memoryType = MEMORY_TYPE_BY_GAME_ID[row.baseId]
  if (!memoryType) {
    warnings.push(`${label}: a Hero Memory type could not be identified from TLIDB and was skipped.`)
    return null
  }
  const rarity = row.rarityValue === null ? undefined : MEMORY_RARITY_BY_LOG_VALUE[row.rarityValue]
  if (!rarity) {
    warnings.push(`${label}: Hero Memory rarity could not be identified and the memory was skipped.`)
    return null
  }
  const source = MEMORY_SOURCE_BY_TYPE[memoryType]
  const baseStatRow = row.baseAttrAffixes[0]
  const baseStat = baseStatRow && catalog
    ? loggedMemoryBaseStatSelection(baseStatRow, catalog, source, catalog.log_affixes, warnings, `${source} base stat`)
    : null
  if (!baseStatRow || !baseStat) {
    warnings.push(`${source}: its base stat is not mapped in the log import data.`)
  }
  const mapPool = (rows: UeLogMemory['fixedAffixes'], pool: HeroMemoryAffix[], group: 'fixed_affixes' | 'random_affixes', label: string) =>
    rows.map(affix => loggedMemorySelection(affix, pool, source, group, catalog?.log_affixes, warnings, `${source} ${label}`))
  const fixed = mapPool(row.fixedAffixes, catalog?.fixed_affixes ?? [], 'fixed_affixes', 'fixed affix')
  const random = mapPool(row.randomAffixes, catalog?.random_affixes ?? [], 'random_affixes', 'random affix')
  const fixedAffixes: CreatedHeroMemory['fixedAffixes'] = [fixed[0] ?? null, fixed[1] ?? null]
  const randomAffixes: CreatedHeroMemory['randomAffixes'] = [random[0] ?? null, random[1] ?? null]
  return {
    id: `ue-log-${row.baseId}-${row.slot ?? 'base'}`,
    memoryType,
    rarity,
    level: row.level ?? undefined,
    baseStat,
    fixedAffixes,
    randomAffixes,
    revived: row.awakenAffixes.length > 0,
    revivalMod: null,
  }
}

function importLoggedMemories(
  character: UeLogCharacterPreview, catalog: UeLogReferenceCatalogs['memories'],
  revivalAffixes: UeLogReferenceCatalogs['revivalAffixes'], warnings: string[],
): { heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]; baseMemory: CreatedHeroMemory | null; memoryInventory: CreatedHeroMemory[] } {
  const byType = new Map<CreatedHeroMemory['memoryType'], CreatedHeroMemory>()
  for (const row of character.memories ?? []) {
    const memory = loggedMemory(row, catalog, warnings, `Memory slot ${row.slot ?? 'unknown'}`)
    if (memory) byType.set(memory.memoryType, memory)
  }
  const heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null] = [
    byType.get('origin') ?? null, byType.get('discipline') ?? null, byType.get('progress') ?? null,
  ]
  const baseMemory = character.baseMemory
    ? loggedMemory(character.baseMemory, catalog, warnings, 'Base Trait Slot')
    : null
  if (baseMemory) {
    const revivedHost = heroMemories.find(memory => memory?.revived)
    if (revivedHost) {
      const boost = character.baseMemory?.affixBoost ?? revivedHost.revivalMod?.rolledValue ?? null
      const type = MEMORY_TYPE_LABEL[baseMemory.memoryType]
      const cap = MEMORY_RARITY_LABEL[baseMemory.rarity]
      const revivalMod = revivalAffixes?.find(entry => entry.source === 'Memory Revival'
        && entry.modifier.includes(`${cap} or lower ${type} Memory`))
      revivedHost.revivalMod = {
        modifier: revivalMod?.modifier
          ?? `Base Traits now have Base Trait slots that can be installed with a ${cap} or lower ${type} Memory. Base Stats and the value of Random Affixes of the Memory installed in this slot`,
        tier: revivalMod?.tier ?? 1,
        ...(revivalMod?.tier_known === false ? { tierKnown: false } : {}),
        rolledValue: boost,
      }
      if (!revivalMod) warnings.push('The revived memory base-slot modifier text could not be matched to TLIDB; its imported penalty is preserved.')
    } else {
      warnings.push('The Base Trait Slot memory was found, but its enabling revived memory was not present in the same login capture.')
    }
  }
  return {
    heroMemories,
    baseMemory,
    memoryInventory: [...heroMemories.filter((memory): memory is CreatedHeroMemory => !!memory), ...(baseMemory ? [baseMemory] : [])],
  }
}

function importLoggedSageTrait(
  character: UeLogCharacterPreview, traits: HeroTrait[] | null | undefined, warnings: string[],
): Pick<Build, 'traitId' | 'advancedTraitSelections'> {
  const knownIds = [1800011, 1800022, 1800031]
  const ids = [...(character.activeTraitIds ?? [])].sort((a, b) => a - b)
  if (character.heroId !== 1800 || ids.length !== knownIds.length || ids.some((id, index) => id !== knownIds[index])) {
    if (ids.length) warnings.push('Hero trait selections in this login could not be matched to TLIDB and were left for manual selection.')
    return {}
  }
  const trait = traits?.find(candidate => candidate.hero === 'Sage' && candidate.variant_name === 'Licorice Note')
  const picks = ['Scent of Ambition', 'Everlasting Nectar']
  if (!trait || picks.some(name => !trait.advanced_traits.some(advanced => advanced.name === name))) {
    warnings.push('Sage’s Licorice Note selections could not be matched to the current TLIDB trait catalog.')
    return {}
  }
  return { traitId: trait.trait_id, advancedTraitSelections: picks }
}

function loggedElixirIngredients(
  character: UeLogCharacterPreview,
  trait: HeroTrait | undefined,
): { ingredients: NonNullable<Build['elixirIngredients']>; unmapped: boolean } {
  const ingredients: NonNullable<Build['elixirIngredients']> = {}
  if (!trait || !character.ingredientChoices?.length) return { ingredients, unmapped: false }
  const ingredientGroups = trait.ingredients ?? []
  const categoryByBottleSlot: Record<number, string[]> = { 2: [], 3: [] }
  const baseGroup = ingredientGroups.find(group => group.trait_name === trait.variant_name)
  const functionalGroup = ingredientGroups.find(group => group.trait_name === 'Pungent Stimulant Salt')
  const specialGroup = ingredientGroups.find(group => group.trait_name === 'Licorice Tincture Blend')
  categoryByBottleSlot[2] = [
    ...(baseGroup?.categories.map(category => category.category) ?? []),
    ...(functionalGroup?.categories.map(category => category.category) ?? []),
  ]
  categoryByBottleSlot[3] = [
    ...(specialGroup?.categories.map(category => category.category) ?? []),
    ...(functionalGroup?.categories.map(category => category.category) ?? []),
  ]
  let unmapped = false
  for (const choice of character.ingredientChoices) {
    const optionPosition = Number(choice.optionId.slice(-2, -1))
    const category = categoryByBottleSlot[choice.bottleSlot]?.[choice.materialSlot - 1]
    const items = ingredientGroups.flatMap(group => group.categories)
      .find(candidate => candidate.category === category)?.items
    const item = Number.isInteger(optionPosition) && optionPosition > 0 ? items?.[optionPosition - 1] : undefined
    if (!category || !item) { unmapped = true; continue }
    ingredients[choice.bottleSlot] ??= {}
    ingredients[choice.bottleSlot][category] = item.name
  }
  return { ingredients, unmapped }
}

type SlatePlacementLayout = { cells: [number, number][] | undefined; orientationIndex: number; originOffset?: [number, number] }
type SlatePlacementInput = { sourceIndex: number; row: UeLogSlate; indexCell: [number, number]; layouts: SlatePlacementLayout[] }
type SlatePlacement = { anchor: [number, number]; cells: [number, number][]; orientationIndex: number }

/** Find the largest compatible slate layout and omit positions that differ across explored solutions. */
export function resolveSlatePlacements(
  prepared: SlatePlacementInput[], maxSearchNodes = 100_000,
): { placements: Map<number, SlatePlacement>; bestSolution: Map<number, SlatePlacement>; ambiguousPlacements: Set<number>; searchLimitReached: boolean; hasSolution: boolean } {
  const current = new Map<number, SlatePlacement>()
  const firstSolution = new Map<number, SlatePlacement>()
  const ambiguousPlacements = new Set<number>()
  let bestPlacedCount = -1
  let searchNodes = 0
  let searchLimitReached = false
  const search = (remaining: SlatePlacementInput[], occupied: Set<string>): boolean => {
    if (++searchNodes > maxSearchNodes) {
      searchLimitReached = true
      return true
    }
    if (current.size + remaining.length < bestPlacedCount) return false
    if (!remaining.length) {
      if (current.size > bestPlacedCount) {
        bestPlacedCount = current.size
        firstSolution.clear()
        ambiguousPlacements.clear()
        for (const [key, value] of current) {
          firstSolution.set(key, { anchor: [...value.anchor], cells: value.cells.map(cell => [...cell]), orientationIndex: value.orientationIndex })
        }
      } else {
        for (const piece of prepared) {
          const first = firstSolution.get(piece.sourceIndex)
          const placement = current.get(piece.sourceIndex)
          if (!!first !== !!placement || (first && placement && JSON.stringify(first) !== JSON.stringify(placement))) {
            ambiguousPlacements.add(piece.sourceIndex)
          }
        }
      }
      return false
    }
    const piece = remaining[0]!
    const [ir, ic] = piece.indexCell
    for (const layout of piece.layouts) for (const [dr, dc] of (layout.originOffset ? [layout.originOffset] : layout.cells ?? [])) {
      if (!layout.cells) continue
      const anchor: [number, number] = [ir - dr, ic - dc]
      const cells = layout.cells.map(([r, c]) => [anchor[0] + r, anchor[1] + c] as [number, number])
      if (cells.some(([r, c]) => r < 0 || r >= 6 || c < 0 || c >= 6
        || !SLATE_BOARD_VALID[r]?.[c] || occupied.has(`${r},${c}`))) continue
      cells.forEach(([r, c]) => occupied.add(`${r},${c}`))
      current.set(piece.sourceIndex, { anchor, cells, orientationIndex: layout.orientationIndex })
      if (search(remaining.slice(1), occupied)) return true
      cells.forEach(([r, c]) => occupied.delete(`${r},${c}`))
      current.delete(piece.sourceIndex)
    }
    // Keep the largest representable subset so one malformed or incompatible slate does not erase
    // every independently placeable slate.
    if (current.size + remaining.length - 1 >= bestPlacedCount && search(remaining.slice(1), occupied)) return true
    return false
  }
  search(prepared, new Set())
  const placements = new Map<number, SlatePlacement>()
  for (const piece of prepared) {
    const placement = firstSolution.get(piece.sourceIndex)
    if (placement && (searchLimitReached || !ambiguousPlacements.has(piece.sourceIndex))) placements.set(piece.sourceIndex, placement)
  }
  return { placements, bestSolution: firstSolution, ambiguousPlacements, searchLimitReached, hasSolution: bestPlacedCount >= 0 }
}

function importLoggedSlates(
  rows: UeLogSlate[], talentTrees: Array<{ name: string; nodes?: { id: string; game_id?: string; column?: number; row?: number; node_type?: string; effects?: string[] }[] }>, pool: SlatePool | null | undefined, warnings: string[],
): NonNullable<Build['slates']> {
  const nodesByGameId = new Map<string, { id: string; treeName: string; nodeType: string; effects: string[] }>()
  for (const tree of talentTrees) for (const node of tree.nodes ?? []) {
    if (node.game_id) nodesByGameId.set(node.game_id, { id: node.id, treeName: tree.name, nodeType: node.node_type ?? '', effects: node.effects ?? [] })
  }
  for (const option of [...(pool?.magic ?? []), ...(pool?.rare ?? []), ...(pool?.legendary ?? [])]) {
    if (option.game_id && !nodesByGameId.has(option.game_id)) {
      nodesByGameId.set(option.game_id, { id: option.nodeId, treeName: option.treeName, nodeType: option.nodeType, effects: option.effects })
    }
  }
  const nodesByCareerPosition = new Map<string, { id: string; treeName: string; nodeType: string; effects: string[] }>()
  for (const [prefix, treeName] of Object.entries(UE_LOG_GAME_ID_TREE_NAMES)) {
    const treeNodes = talentTrees.find(tree => tree.name === treeName)?.nodes ?? []
    // Only use encoded coordinates when this season's tree data has no game IDs to join.
    if (treeNodes.length === 0 || treeNodes.some(node => node.game_id)) continue
    for (const node of treeNodes) {
      if (node.column === undefined || node.row === undefined) continue
      nodesByCareerPosition.set(`${prefix}:${node.column}:${node.row}`, {
        id: node.id, treeName, nodeType: node.node_type ?? '', effects: node.effects ?? [],
      })
    }
  }
  const nodeForGameId = (gameId: string) => {
    const exact = nodesByGameId.get(gameId)
    if (exact) return exact
    const coordinates = loggedTalentCoordinates(gameId)
    const prefix = gameId.slice(0, 2)
    return coordinates ? nodesByCareerPosition.get(`${prefix}:${coordinates.column}:${coordinates.row}`) : undefined
  }
  const kindByUniqueId: Record<number, string> = { 1003: 'fallen_starlight', 1005: 'corner_of_divinity', 1010: 'pedigree' }
  const treeByBaseId: Record<number, string> = { 260504: 'God of Might', 260304: 'God of War', 260306: 'God of War' }
  const coreByGameId = new Map((pool?.core ?? []).flatMap(core => core.game_id ? [[core.game_id, core] as const] : []))
  const loggedTalentSlots = (row: UeLogSlate, kind: string) => {
    if ((kind === 'base' || kind === 'nether_kings_divinity') && (row.baseTalentIds.length > 0 || row.enchantTalentIds.length > 0)) {
      const fixed = row.baseTalentIds.map((gameId, slotIndex) => ({ gameId, slotIndex }))
      const branded = row.enchantTalentIds.length > 0
        ? row.enchantTalentIds.map((gameId, index) => ({ gameId, slotIndex: index + 2 }))
        : (() => {
          const compactBrandedList = row.talentSlots.length === 3
            && row.talentSlots.every((slot, index) => (slot.slotIndex ?? index) < 3)
            && !row.talentSlots.some(slot => slot.talentId && row.baseTalentIds.includes(slot.talentId))
          return row.talentSlots.flatMap((slot, arrayIndex) => {
            if (!slot.talentId || (slot.slotIndex ?? arrayIndex) < 2 && row.baseTalentIds.includes(slot.talentId)) return []
            const sourceIndex = slot.slotIndex ?? arrayIndex
            if (compactBrandedList) return [{ gameId: slot.talentId, slotIndex: sourceIndex + 2 }]
            return [{ gameId: slot.talentId, slotIndex: sourceIndex }]
          })
        })()
      return [...fixed, ...branded]
    }
    return row.talentSlots.some(slot => slot.talentId)
      ? row.talentSlots.flatMap((slot, arrayIndex) => slot.talentId ? [{ gameId: slot.talentId, slotIndex: slot.slotIndex ?? arrayIndex }] : [])
      : [...row.baseTalentIds, ...row.enchantTalentIds].map((gameId, slotIndex) => ({ gameId, slotIndex }))
  }
  const prepared = rows.map((row, sourceIndex) => {
    const baseVariant = NETHER_KING_VARIANT_BY_BASE_ID[row.baseId ?? -1]
    const kind = baseVariant ? 'nether_kings_divinity'
      : row.uniqueItemId && row.uniqueItemId !== 0 ? kindByUniqueId[row.uniqueItemId] : 'base'
    const shapeIndex = kind === 'base' ? ({ 1033: 1, 1035: 1, 1043: 4, 1045: 4 } as Record<number, number>)[row.shapeId ?? -1] : 0
    const gameIdSlots = loggedTalentSlots(row, kind ?? 'base')
    const taggedVariants = kind === 'nether_kings_divinity' ? [...new Set(gameIdSlots.flatMap(({ gameId, slotIndex }) => {
      if (slotIndex < 2) return []
      const variant = netherKingBrandVariant(coreByGameId.get(gameId)?.effects ?? [])
      return variant ? [variant] : []
    }))] : []
    const netherKingVariant: NetherKingVariant = baseVariant ?? (taggedVariants.length === 1 ? taggedVariants[0]! : 'judgment')
    const orientationCount = kind === 'base' ? 4 : LEGENDARY_ORIENTATIONS[kind ?? '']?.length ?? 1
    const rawOrientation = kind === 'base' ? (row.direction ?? 0) : row.direction === null ? -1 : row.direction - 1
    // Square-grid shapes have 1, 2, or 4 distinct rotations; only those counts can safely collapse the game's four directions.
    const canCollapseSymmetricRotations = orientationCount === 1 || orientationCount === 2 || orientationCount === 4
    const orientationIndex = kind !== 'base' && rawOrientation >= 0 && rawOrientation < 4 && canCollapseSymmetricRotations
      ? rawOrientation % orientationCount
      : rawOrientation
    if (kind !== 'base' && canCollapseSymmetricRotations && rawOrientation >= orientationCount && rawOrientation < 4) {
      warnings.push(`Slate ${row.uniqueItemId ?? row.shapeId ?? ''}: symmetric-shape direction mapping is inferred; confirm orientation ${row.direction}.`)
    }
    const layouts: { cells: [number, number][] | undefined; orientationIndex: number; originOffset?: [number, number] }[] = kind === 'nether_kings_divinity'
      ? netherKingVariant === 'judgment'
        ? (LEGENDARY_ORIENTATIONS[kind] ?? []).map((cells, index) => ({ cells, orientationIndex: index, originOffset: NETHER_KING_ORIGIN_OFFSETS[index] }))
        : [{
          cells: netherKingOrientationCells(netherKingVariant, 0), orientationIndex: 0,
          originOffset: netherKingVariant === 'contamination' ? [0, 0] : [0, 2],
        }]
      : [{ cells: kind === 'base' ? BASE_SLATE_SHAPES[shapeIndex ?? -1]?.rotations[orientationIndex] : LEGENDARY_ORIENTATIONS[kind ?? '']?.[orientationIndex], orientationIndex }]
    const cellsShape = layouts[0]?.cells
    if (!kind) {
      warnings.push(row.baseId !== null && NETHER_KING_VARIANT_BY_BASE_ID[row.baseId]
        ? `Nether King's Divinity: the game log does not include its branded board shape, so it could not be placed.`
        : `Slate ${row.uniqueItemId ?? row.shapeId ?? ''}: kind or ShapeId is not mapped from observed log data and was left out.`)
      return null
    }
    if (kind !== 'nether_kings_divinity' && (orientationIndex < 0 || orientationIndex >= orientationCount)) {
      warnings.push(`Slate ${row.uniqueItemId ?? row.shapeId ?? ''}: logged direction ${row.direction ?? 'missing'} is outside the verified range and was left out.`)
      return null
    }
    if (!cellsShape) {
      warnings.push(`Slate ${row.uniqueItemId ?? row.shapeId ?? ''}: kind or ShapeId is not mapped from observed log data and was left out.`)
      return null
    }
    if (row.index === null || row.index < 1) {
      warnings.push('An equipped slate has no valid board index and was left out.')
      return null
    }
    if (kind === 'corner_of_divinity') {
      warnings.push(`A Corner of Divinity at board index ${row.index}: its direction mapping is inferred from other unique slates; confirm its orientation.`)
    }
    if (kind === 'base') {
      warnings.push(`Base slate at board index ${row.index}: the ShapeId ${row.shapeId} shape and direction mapping is inferred; confirm its placement.`)
    }
    // The log encodes Index as SlotId=10*column+row (1-based); it identifies a cell occupied by the piece.
    return { row, sourceIndex, kind, shapeIndex: shapeIndex ?? 0, orientationIndex, layouts, netherKingVariant, taggedVariants,
      indexCell: [(row.index - 1) % 10, Math.floor((row.index - 1) / 10) - 1] as [number, number] }
  }).filter((piece): piece is NonNullable<typeof piece> => !!piece)
  const { placements: resolvedPlacements, bestSolution, ambiguousPlacements, searchLimitReached, hasSolution } = resolveSlatePlacements(prepared)
  if (searchLimitReached) {
    warnings.push('Slate placement search reached its safety limit. The best arrangement found so far was imported; review slate positions in the draft.')
    for (const piece of prepared) {
      if (bestSolution.has(piece.sourceIndex)) {
        if (ambiguousPlacements.has(piece.sourceIndex)) {
          warnings.push(`Slate at board index ${piece.row.index}: its best-known position was imported, but the placement search hit its limit before ambiguity could be resolved.`)
        }
      } else {
        warnings.push(`Slate at board index ${piece.row.index}: no position was found before the placement search limit; review the imported board.`)
      }
    }
  } else if (hasSolution) {
    for (const piece of prepared) {
      if (ambiguousPlacements.has(piece.sourceIndex)) {
        warnings.push(`Slate at board index ${piece.row.index}: its anchor is ambiguous among the best-fitting layouts and was left out.`)
      } else if (!bestSolution.has(piece.sourceIndex)) {
        warnings.push(`Slate at board index ${piece.row.index}: it could not fit with the other logged slates and was left out.`)
      }
    }
  }
  return prepared.flatMap(piece => {
    const { row, sourceIndex: index, kind, shapeIndex } = piece
    const placement = resolvedPlacements.get(index)
    if (!placement) return []
    const { anchor, cells, orientationIndex } = placement
    const gameIdSlots = loggedTalentSlots(row, kind)
    const gameIds = gameIdSlots.map(slot => slot.gameId)
    const slots = initSlateSlots(kind).map(slot => ({ ...slot })) as SavedSlateSlot[]
    gameIdSlots.forEach(({ gameId, slotIndex }) => {
      const slot = slots[slotIndex]
      if (!slot) {
        warnings.push(`Slate at board index ${row.index}: logged talent ${gameId} exceeds the Builder's ${kind} slots and was left out.`)
        return
      }
      const core = coreByGameId.get(gameId)
      const node = nodeForGameId(gameId)
      if (core) {
        if (!slot.canBeCore) {
          warnings.push(`Slate at board index ${row.index}: ${core.name} is a Core Talent, but the Builder's ${kind} slate has no Core Talent slot; it was left out.`)
          return
        }
        Object.assign(slot, { isCore: true, selectedCoreKey: core.key, coreName: core.name, effects: core.effects })
        return
      }
      if (!node) {
        warnings.push(`Slate at board index ${row.index}: talent ${gameId} could not be matched to a current tree node and was left empty.`)
        return
      }
      const category = (['magic', 'rare', 'legendary'] as const).find(type =>
        (pool?.[type] ?? []).some(option => option.game_id === gameId))
        ?? (node.nodeType.includes('Legendary Medium') ? 'legendary' : node.nodeType.includes('Medium') ? 'rare' : 'magic')
      const rank: Record<typeof category, number> = { magic: 0, rare: 1, legendary: 2 }
      if (rank[category] > rank[slot.maxType]) {
        warnings.push(`Slate at board index ${row.index}: ${node.nodeType || category} does not fit slot ${slotIndex + 1} on ${kind}; it was left empty.`)
        return
      }
      Object.assign(slot, { isCore: false, slotType: category, selectedNodeId: node.id, effects: node.effects, nodeType: node.nodeType })
    })
    const treeType = kind === 'nether_kings_divinity' ? 'Nether King'
      : treeByBaseId[row.baseId ?? -1] ?? gameIds.map(id => nodeForGameId(id)?.treeName ?? coreByGameId.get(id)?.treeName).find(Boolean)
    if (kind === 'base' && !treeType) warnings.push(`Slate at board index ${row.index}: its talent tree could not be identified from the base item or selected talent IDs; choose the tree manually.`)
    if (kind === 'nether_kings_divinity') {
      if (piece.netherKingVariant !== 'judgment' || orientationIndex !== 0) {
        const variantLabel = `${piece.netherKingVariant[0]!.toUpperCase()}${piece.netherKingVariant.slice(1)}`
        warnings.push(`Nether King's Divinity at board index ${row.index}: its ${variantLabel} placement is inferred from the occupied cell; review its board position.`)
      }
      if (!NETHER_KING_VARIANT_BY_BASE_ID[row.baseId ?? -1] && piece.taggedVariants.length === 0) {
        warnings.push(`Nether King's Divinity at board index ${row.index}: the log does not identify its variant; imported as Judgment. Confirm the variant and board placement.`)
      } else if (!NETHER_KING_VARIANT_BY_BASE_ID[row.baseId ?? -1] && piece.taggedVariants.length > 1) {
        warnings.push(`Nether King's Divinity at board index ${row.index}: its branded talents identify conflicting variants; imported as Judgment. Confirm the variant and board placement.`)
      } else if (NETHER_KING_VARIANT_BY_BASE_ID[row.baseId ?? -1] && piece.taggedVariants.some(variant => variant !== piece.netherKingVariant)) {
        warnings.push(`Nether King's Divinity at board index ${row.index}: its BaseId variant conflicts with a branded talent tag; confirm the variant.`)
      }
    }
    return [{ id: `ue-log-slate-${row.index}-${index}`, kind, cells, orientationIndex,
      shapeIndex, anchor, slots, ...(treeType ? { treeType } : {}),
      ...(kind === 'nether_kings_divinity' ? { netherKingVariant: piece.netherKingVariant } : {}) }]
  })
}

function importLoggedPrisms(
  character: UeLogCharacterPreview,
  talentTrees: Array<{ name: string; nodes?: { id: string; game_id?: string; column?: number; row?: number }[] }>,
  catalog: PrismCatalog | null | undefined, warnings: string[],
): NonNullable<Build['prisms']> {
  const enriched = catalog?.catalog
  return (character.talentTrees ?? []).flatMap((loggedTree, index) => {
    const row = loggedTree.prism
    if (!row) return []
    const item = enriched?.items.find(candidate => candidate.game_id === row.baseId)
    const allNodes = talentTrees.flatMap(tree => (tree.nodes ?? []).map(node => ({ ...node, treeName: tree.name })))
    const mappedTreeName = loggedTree.careerId === null ? undefined : UE_LOG_CAREER_TREE_NAMES[loggedTree.careerId]
    const anchorPosition = row.anchorTalentId ? loggedTalentCoordinates(row.anchorTalentId) : null
    const anchorPrefix = row.anchorTalentId?.slice(0, 2)
    const exactAnchor = allNodes.find(node => node.game_id === row.anchorTalentId)
    const inferredAnchor = !exactAnchor && mappedTreeName && anchorPosition ? allNodes.find(node => node.treeName === mappedTreeName
        && !node.game_id && node.column === anchorPosition.column && node.row === anchorPosition.row
        && anchorPrefix === UE_LOG_CAREER_GAME_ID_PREFIXES[loggedTree.careerId ?? -1]) : undefined
    const anchor = exactAnchor ?? inferredAnchor
    if (!enriched || !item || !anchor) {
      warnings.push(`Ethereal Prism ${row.baseId ?? ''}: its item or anchor talent could not be matched to current canonical data; it was left out.`)
      return []
    }
    const anchorCol = anchor.column ?? anchorPosition?.column
    const anchorRow = anchor.row ?? anchorPosition?.row
    if (anchorCol === undefined || anchorRow === undefined) {
      warnings.push(`${item.name}: its anchor has no usable grid coordinates; the prism was left out.`)
      return []
    }
    if (inferredAnchor) warnings.push(`${item.name}: its anchor was matched by inferred grid coordinates; confirm the imported position.`)
    const mappedRarity = row.rarityValue === 3 ? 'rare' : null
    const rarity = mappedRarity && item.rarities.includes(mappedRarity) ? mappedRarity : item.default_rarity
    if (row.rarityValue !== null && (!mappedRarity || !item.rarities.includes(mappedRarity))) {
      warnings.push(`${item.name}: logged prism rarity ${row.rarityValue} has no verified mapping; the catalog default was used.`)
    }
    const ids = new Set([...row.prefixAffixes, ...row.baseAffixes, ...row.baseAttrAffixes].flatMap(affix => affix.id ? [affix.id] : []))
    const matches = (affix: { modifier_id?: string | null; modifier_ids?: string[] }) =>
      (!!affix.modifier_id && ids.has(affix.modifier_id)) || (affix.modifier_ids ?? []).some(id => ids.has(id))
    const area = enriched.area_size.find(matches)
    const middle = enriched.middle.find(matches)
    const advanced = [...enriched.advanced, ...(enriched.do_not_replace[item.short_name] ?? [])].find(matches)
    const implicit = item.implicit.kind === 'add_choice'
      ? catalog?.base_affix_modifiers?.find(affix => matches(affix))?.modifier ?? ''
      : item.implicit.text ?? ''
    if (!implicit) warnings.push(`${item.name}: the logged implicit option could not be matched to current catalog data.`)
    for (const affix of row.prefixAffixes) {
      const knownAffixId = affix.id && [area, middle, advanced].some(candidate => candidate
        && (candidate.modifier_id === affix.id || candidate.modifier_ids?.includes(affix.id!)))
      if (affix.id && !knownAffixId) {
        warnings.push(`${item.name}: prism affix ${affix.id} is missing from the current prism catalog and was left out.`)
      }
      if (affix.values.length) warnings.push(`${item.name}: logged prism affix roll values are not stored by the current Builder prism configuration.`)
    }
    if ([...row.baseAffixes, ...row.baseAttrAffixes].some(affix => affix.values.length)) {
      warnings.push(`${item.name}: logged prism implicit roll values are not stored by the current Builder prism configuration.`)
    }
    const positions = row.effectPositions.map(({ x, y }) => ({ col: y - 1, row: x - 1 }))
    const boxCols = positions.length ? Math.max(...positions.map(p => p.col)) - Math.min(...positions.map(p => p.col)) + 1 : undefined
    const boxRows = positions.length ? Math.max(...positions.map(p => p.row)) - Math.min(...positions.map(p => p.row)) + 1 : undefined
    if (area && positions.length === 0) {
      warnings.push(`${item.name}: no prism area cells were logged; imported area uses the matched ${area.cols} by ${area.rows} modifier.`)
    } else if (area && (boxCols !== area.cols || boxRows !== area.rows)) {
      warnings.push(`${item.name}: logged area spans ${boxCols} columns by ${boxRows} rows, but the matched modifier says ${area?.cols} by ${area?.rows}; imported area follows the logged cells.`)
    }
    return [{
      id: `ue-log-prism-${row.baseId}-${index}`, templateId: `ue-log-prism-template-${row.baseId}-${index}`,
      kind: 'ethereal_prism', name: item.name, iconUrl: item.icon_url,
      rolls: { micro: -100, medium: -100, legendary: -100 },
      ethereal: { shortName: item.short_name, rarity, implicit, tintWhenRare: item.tint_when_rare,
        ...(area ? { areaSize: area.modifier, boxCols: boxCols ?? area.cols, boxRows: boxRows ?? area.rows } : boxCols && boxRows ? { boxCols, boxRows } : {}),
        ...(middle ? { middle: middle.modifier } : {}), ...(advanced ? { advanced: advanced.modifier } : {}),
        ...(row.replacementTalentId ? { replacementTalentId: row.replacementTalentId } : {}) },
      // Ethereal prisms change effects on the real allocated tree nodes. The Builder's boxAllocations field
      // represents Inverse Image copies only; keep it empty here.
      treeName: anchor.treeName, anchorCol, anchorRow, boxAllocations: {},
    }]
  })
}

/** Create an editable Builder draft from the game data that can be joined by logged IDs. */
export function createUeLogBuild(
  character: UeLogCharacterPreview,
  grafts: Graft[],
  legendaryItems: LegendaryGearItem[],
  craftBaseItems: CraftBaseItemGroup[] = [],
  craftBaseTypes: CraftBaseType[] = [],
  towerSequences: TowerSequenceEntry[] = [],
  skillCatalog: SkillItem[] = [],
  beltBlends: BeltBlend[] = [],
  talentTrees: Array<{
    name: string
    nodes?: { id: string; game_id?: string; column?: number; row?: number; node_type?: string; effects?: string[]; trait_variants?: { game_id?: string }[] }[]
    core_talent_slots?: { options: { id: string; name: string; effects: string[] }[] }[]
  }> = [],
  pactSpiritCatalog: PactSpirit[] = [],
  referenceCatalogs: UeLogReferenceCatalogs = {},
): UeLogBuildResult {
  const warnings: string[] = []
  const gear: EquippedGearItem[] = []
  let unmappedGearCount = 0
  for (const item of character.gear) {
    const graft = grafts.find(candidate => candidate.game_id === item.baseId)
    if (graft) {
      gear.push(mapTowerSequence(item, buildVoraxItem(item, graft, legendaryItems, warnings, beltBlends), towerSequences, warnings))
      continue
    }

    const unique = item.uniqueItemId === null
      ? null
      : legendaryItems.find(candidate => candidate.game_id === item.uniqueItemId) ?? null
    if (unique) {
      gear.push(mapTowerSequence(item, buildUniqueItem(item, unique, craftBaseItems, craftBaseTypes, legendaryItems, warnings, beltBlends), towerSequences, warnings))
      continue
    }

    const foundBase = findCraftBase(item.baseId, craftBaseItems)
    if (foundBase) {
      const craftType = craftBaseTypes.find(candidate => candidate.item_id === foundBase.group.item_id)
      if (!craftType) {
        warnings.push(`${foundBase.item.name}: base item data loaded without its craft affix table.`)
      }
      gear.push(mapTowerSequence(item, buildCraftedItem(item, foundBase.item, craftBaseTypes, legendaryItems, warnings, beltBlends), towerSequences, warnings))
      continue
    }

    if (item.baseId !== null) unmappedGearCount++
  }

  if (unmappedGearCount > 0) {
    warnings.push(`${unmappedGearCount} equipped gear item${unmappedGearCount === 1 ? '' : 's'} could not be identified in the current Builder data.`)
  }
  const skills = buildLoggedSkills(character.skills ?? [], skillCatalog, warnings)
  const treeByGameId = new Map<string, { treeName: string; nodeId: string }>()
  for (const tree of talentTrees) {
    for (const node of tree.nodes ?? []) {
      if (node.game_id) treeByGameId.set(node.game_id, { treeName: tree.name, nodeId: node.id })
      for (const variant of node.trait_variants ?? []) {
        if (variant.game_id) treeByGameId.set(variant.game_id, { treeName: tree.name, nodeId: node.id })
      }
    }
  }
  const slots: Build['slots'] = [null, null, null, null]
  let unmappedTalentCount = 0
  let inferredTalentCount = 0
  for (const [index, loggedTree] of (character.talentTrees ?? []).entries()) {
    const mappedNodes = loggedTree.allocations.flatMap(allocation => {
      const known = treeByGameId.get(allocation.id)
      const treeName = loggedTree.careerId === null ? undefined : UE_LOG_CAREER_TREE_NAMES[loggedTree.careerId]
      const expectedPrefix = UE_LOG_CAREER_GAME_ID_PREFIXES[loggedTree.careerId ?? -1]
      const coordinates = allocation.id.slice(0, 2) === expectedPrefix ? loggedTalentCoordinates(allocation.id) : null
      const positioned = treeName && coordinates ? talentTrees.find(tree => tree.name === treeName)?.nodes?.find(node =>
        !node.game_id && node.column === coordinates.column && node.row === coordinates.row) : undefined
      if (!known && positioned) inferredTalentCount++
      const node = known ?? (positioned ? { treeName: treeName!, nodeId: positioned.id } : undefined)
      if (!node) {
        unmappedTalentCount++
        return []
      }
      return [{ ...allocation, ...node }]
    })
    const coreOptions = (loggedTree.coreTalentSelections ?? []).map(gameId => ({
      gameId,
      option: referenceCatalogs.slatePool?.core.find(candidate => candidate.game_id === gameId),
    }))
    const treeName = mappedNodes[0]?.treeName ?? coreOptions.find(row => row.option)?.option?.treeName
    if (!treeName) {
      for (const { gameId } of coreOptions) warnings.push(`Core talent ${gameId} could not be associated with a current talent tree and was skipped.`)
      continue
    }
    if (mappedNodes.some(node => node.treeName !== treeName)) {
      warnings.push(`Logged talent allocations for career ${loggedTree.careerId ?? 'unknown'} span multiple trees; only the first tree was imported.`)
    }
    const nodeStates = Object.fromEntries(mappedNodes.filter(node => node.treeName === treeName).map(node => [node.nodeId, node.rank]))
    const coreTalentSelections: Record<string, string> = {}
    for (const { gameId, option } of coreOptions) {
      if (!option) {
        warnings.push(`Core talent ${gameId} could not be matched to the current catalog and was skipped.`)
        continue
      }
      if (option.treeName !== treeName) {
        warnings.push(`Core talent ${option.name} belongs to ${option.treeName}, not ${treeName}; it was skipped.`)
        continue
      }
      const detail = talentTrees.find(tree => tree.name === treeName)
      const key = option.key.startsWith(`${treeName}:`) ? option.key.slice(treeName.length + 1).replace(/#\d+$/, '') : ''
      const slotIndex = detail?.core_talent_slots?.findIndex(slot => slot.options.some(candidate =>
        candidate.id === key || (candidate.name === option.name && JSON.stringify(candidate.effects) === JSON.stringify(option.effects)))) ?? -1
      const selected = slotIndex >= 0 ? detail?.core_talent_slots?.[slotIndex]?.options.find(candidate =>
        candidate.id === key || (candidate.name === option.name && JSON.stringify(candidate.effects) === JSON.stringify(option.effects))) : undefined
      if (!selected) {
        warnings.push(`Core talent ${option.name} could not be matched to a selectable slot in ${treeName} and was skipped.`)
        continue
      }
      coreTalentSelections[String(slotIndex)] = selected.id
    }
    if (index < slots.length) slots[index] = { treeName, nodeStates, ...(Object.keys(coreTalentSelections).length ? { coreTalentSelections } : {}) }
    else warnings.push(`Talent tree ${treeName} exceeded Builder's four tree slots and was skipped.`)
  }
  if (unmappedTalentCount) {
    warnings.push(`${unmappedTalentCount} allocated talent node${unmappedTalentCount === 1 ? '' : 's'} could not be matched to current TLIDB data and ${unmappedTalentCount === 1 ? 'was' : 'were'} skipped.`)
  }
  if (inferredTalentCount) {
    warnings.push(`${inferredTalentCount} allocated talent node${inferredTalentCount === 1 ? ' was' : 's were'} matched by inferred grid coordinates; confirm ${inferredTalentCount === 1 ? 'that node' : 'those nodes'} in the imported tree.`)
  }
  const importedSlates = importLoggedSlates(character.slates ?? [], talentTrees, referenceCatalogs.slatePool, warnings)
  const importedPrisms = importLoggedPrisms(character, talentTrees, referenceCatalogs.etherealPrisms, warnings)
  // player.FollowServant identifies the cosmetic pet, not the combat follower. The log does not expose
  // the mercenary selection, so do not turn that unrelated pet value into an import warning.
  const importedPactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null] = [null, null, null]
  for (const contract of character.pactContracts ?? []) {
    if (contract.areaId < 1 || contract.areaId > 3) continue
    const byGameId = pactSpiritCatalog.find(candidate => candidate.game_id === contract.servantId)
    const overrideItemId = UE_LOG_PACT_SPIRIT_ITEM_OVERRIDES[contract.servantId]
    const spirit = byGameId ?? (overrideItemId
      ? pactSpiritCatalog.find(candidate => candidate.item_id === overrideItemId)
      : undefined)
    if (!spirit) {
      warnings.push(`The pact spirit in battle slot ${contract.areaId} is not present in the current TLIDB catalog.`)
      continue
    }
    if (contract.rank === null) {
      warnings.push(`${spirit.name}: the login captures do not include its rank; rank 1 was used.`)
    }
    importedPactSpirits[contract.areaId - 1] = { itemId: spirit.item_id, rank: contract.rank ?? 1 }
  }
  const importedMemories = importLoggedMemories(character, referenceCatalogs.memories, referenceCatalogs.revivalAffixes, warnings)
  const importedTrait = importLoggedSageTrait(character, referenceCatalogs.traits, warnings)
  const traitCatalogEntry = referenceCatalogs.traits?.find(candidate => candidate.trait_id === importedTrait.traitId)
  const elixir = loggedElixirIngredients(character, traitCatalogEntry)
  const traitSlotLevels = deriveTraitSlotLevels(importedMemories.heroMemories, [1, 1, 1, 1], importedMemories.baseMemory)
  if (importedTrait.traitId === 'licorice_note' && !character.ingredientChoices?.length) {
    warnings.push('No Scent Bottle ingredient choices were found in these login captures; review them in Hero Trait after import.')
  } else if (elixir.unmapped) {
    warnings.push('One or more Scent Bottle ingredients could not be matched to the current TLIDB catalog; review them in Hero Trait after import.')
  }
  const truncatedSectionCount = character.truncatedSections?.length ?? 0
  if (truncatedSectionCount > 0) {
    warnings.push(
      'The game log omitted some player data, so slate placement, equipped skill details, or pact spirit ranks may be incomplete.',
    )
  }

  return {
    build: {
      name: `${character.characterName || `Hero ${character.heroId ?? 'unknown'}`} · Level ${character.level ?? 'unknown'}`,
      slots,
      ...(importedSlates.length ? { slates: importedSlates } : {}),
      ...(importedPrisms.length ? { prisms: importedPrisms } : {}),
      gear,
      skills,
      ...importedTrait,
      elixirIngredients: elixir.ingredients,
      traitSlotLevels,
      heroMemories: importedMemories.heroMemories,
      baseMemory: importedMemories.baseMemory,
      memoryInventory: importedMemories.memoryInventory,
      pactSpirits: importedPactSpirits,
      conditionState: { level: character.level ?? 100 },
      characterLevel: character.level ?? 100,
      notes: 'Imported from UE_game.log. Review the imported gear and build settings.',
    },
    warnings,
  }
}
