import { deriveTraitSlotLevels, type Build, type CraftBaseItemGroup, type CraftBaseType, type CreatedHeroMemory, type EquippedGearItem, type EquippedSkill, type EquippedSupportSkill, type GearSlot, type Graft, type HeroMemoryAffix, type HeroTrait, type LegendaryAffix, type LegendaryGearItem, type MemorySlotSelection, type MemoryRarity, type SkillItem, type TowerSequenceEntry, type BeltBlend, type PactSpirit, type SelectedPactSpirit } from '../../api/client'
import type { UeLogCharacterPreview, UeLogGearItem, UeLogMemory, UeLogPactContract, UeLogSkillItem } from './parse'

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
  } | null
  traits?: HeroTrait[] | null
  revivalAffixes?: HeroMemoryAffix[] | null
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
  return `This character has ${loginCount} login captures. Later entries replace earlier gear, skill, memory, contract, and scent bottle slots. Earlier entries fill slots missing from later captures. Talent allocations and servant inventory are combined.`
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
    const talentsByCareer = new Map<number | null, Map<string, { id: string; rank: number }>>()
    for (const talentTree of [...(previous?.preview.talentTrees ?? []), ...(capture.preview.talentTrees ?? [])]) {
      const nodes = talentsByCareer.get(talentTree.careerId) ?? new Map<string, { id: string; rank: number }>()
      for (const allocation of talentTree.allocations) nodes.set(allocation.id, allocation)
      talentsByCareer.set(talentTree.careerId, nodes)
    }
    const servantIds = new Set([
      ...(previous?.preview.servantIds ?? []),
      ...(capture.preview.servantIds ?? []),
    ])
    const truncatedSections = new Set([
      ...(previous?.preview.truncatedSections ?? []),
      ...capture.preview.truncatedSections,
    ])
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
    groups.set(key, {
      fileNumber: capture.fileNumber,
      preview: {
        ...capture.preview,
        gear: [...gearBySlot.values()].sort((a, b) => (a.equippedSlot ?? Number.MAX_SAFE_INTEGER) - (b.equippedSlot ?? Number.MAX_SAFE_INTEGER)),
        skills: [...skillsBySlot.values()].sort((a, b) => a.logIndex - b.logIndex),
        ...(talentsByCareer.size ? { talentTrees: [...talentsByCareer].map(([careerId, nodes]) => ({ careerId, allocations: [...nodes.values()] })) } : {}),
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
  warnings: string[], label: string,
): MemorySlotSelection | null {
  const match = pool.find(candidate => candidate.source === source
    && (candidate as HeroMemoryAffix & { modifier_id?: string | null }).modifier_id === row.id)
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
  source: string, warnings: string[], label: string,
): MemorySlotSelection | null {
  const crosswalk = catalog.log_base_stats?.find(entry => entry.log_modifier_id === row.id && entry.source === source)
  if (!crosswalk) return loggedMemorySelection(row, catalog.base_stats, source, warnings, label)

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
    ? loggedMemoryBaseStatSelection(baseStatRow, catalog, source, warnings, `${source} base stat`)
    : null
  if (!baseStatRow || !baseStat) {
    warnings.push(`${source}: its base stat is not mapped in the log import data.`)
  }
  const mapPool = (rows: UeLogMemory['fixedAffixes'], pool: HeroMemoryAffix[], group: string) =>
    rows.map(affix => loggedMemorySelection(affix, pool, source, warnings, `${source} ${group}`))
  const fixed = mapPool(row.fixedAffixes, catalog?.fixed_affixes ?? [], 'fixed affix')
  const random = mapPool(row.randomAffixes, catalog?.random_affixes ?? [], 'random affix')
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
  talentTrees: Array<{ name: string; nodes?: { id: string; game_id?: string; trait_variants?: { game_id?: string }[] }[] }> = [],
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
  for (const [index, loggedTree] of (character.talentTrees ?? []).entries()) {
    const mappedNodes = loggedTree.allocations.flatMap(allocation => {
      const node = treeByGameId.get(allocation.id)
      if (!node) {
        unmappedTalentCount++
        return []
      }
      return [{ ...allocation, ...node }]
    })
    const treeName = mappedNodes[0]?.treeName
    if (!treeName) continue
    if (mappedNodes.some(node => node.treeName !== treeName)) {
      warnings.push(`Logged talent allocations for career ${loggedTree.careerId ?? 'unknown'} span multiple trees; only the first tree was imported.`)
    }
    const nodeStates = Object.fromEntries(mappedNodes.filter(node => node.treeName === treeName).map(node => [node.nodeId, node.rank]))
    if (index < slots.length) slots[index] = { treeName, nodeStates }
    else warnings.push(`Talent tree ${treeName} exceeded Builder's four tree slots and was skipped.`)
  }
  if (unmappedTalentCount) {
    warnings.push(`${unmappedTalentCount} allocated talent node${unmappedTalentCount === 1 ? '' : 's'} could not be matched to current TLIDB data and ${unmappedTalentCount === 1 ? 'was' : 'were'} skipped.`)
  }
  // player.FollowServant identifies the cosmetic pet, not the combat follower. The log does not expose
  // the mercenary selection, so do not turn that unrelated pet value into an import warning.
  const importedPactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null] = [null, null, null]
  for (const contract of character.pactContracts ?? []) {
    if (contract.areaId < 1 || contract.areaId > 3) continue
    const spirit = pactSpiritCatalog.find(candidate => candidate.game_id === contract.servantId)
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
      'The game log omitted some player data, so a few equipped skill details and pact spirit ranks may be incomplete.',
    )
  }

  return {
    build: {
      name: `${character.characterName || `Hero ${character.heroId ?? 'unknown'}`} · Level ${character.level ?? 'unknown'}`,
      slots,
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
