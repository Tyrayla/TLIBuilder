import type { Build, CraftBaseItemGroup, CraftBaseType, EquippedGearItem, EquippedSkill, EquippedSupportSkill, GearSlot, Graft, LegendaryAffix, LegendaryGearItem, SkillItem, TowerSequenceEntry, BeltBlend } from '../../api/client'
import type { UeLogCharacterPreview, UeLogGearItem, UeLogSkillItem } from './parse'

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

export function describeUeLogCaptureMerge(loginCount: number): string {
  return `This character has ${loginCount} login captures. Later entries replace earlier data in the same gear and skill slots. Earlier entries fill slots missing from later captures. Talent allocations and servant inventory are combined, and the latest recorded follower selection is used.`
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
    const talentsById = new Map<string, { id: string; rank: number }>()
    for (const talent of previous?.preview.talentTreeAllocations ?? []) talentsById.set(talent.id, talent)
    for (const talent of capture.preview.talentTreeAllocations ?? []) talentsById.set(talent.id, talent)
    const servantIds = new Set([
      ...(previous?.preview.servantIds ?? []),
      ...(capture.preview.servantIds ?? []),
    ])
    const truncatedSections = new Set([
      ...(previous?.preview.truncatedSections ?? []),
      ...capture.preview.truncatedSections,
    ])
    groups.set(key, {
      fileNumber: capture.fileNumber,
      preview: {
        ...capture.preview,
        gear: [...gearBySlot.values()].sort((a, b) => (a.equippedSlot ?? Number.MAX_SAFE_INTEGER) - (b.equippedSlot ?? Number.MAX_SAFE_INTEGER)),
        skills: [...skillsBySlot.values()].sort((a, b) => a.logIndex - b.logIndex),
        talentTreeAllocations: [...talentsById.values()],
        followServantId: capture.preview.followServantId ?? previous?.preview.followServantId ?? null,
        servantIds: [...servantIds],
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
  if (!slot) warnings.push(`Gear base ${item.baseId ?? 'unknown'}: equipped slot ${item.equippedSlot ?? 'unknown'} was not recognized.`)
  return slot
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
}

function warnUnsupportedLogAffixes(item: UeLogGearItem, name: string, warnings: string[], beltBlends: BeltBlend[] = []) {
  for (const id of item.enchantAffixes.flatMap(row => row.id ? [row.id] : [])) {
    if (item.equippedSlot === 8 && beltBlends.some(blend => blend.modifier_id === id)) continue
    warnings.push(`${name}: enchant affix ${id} is not in the current Builder catalogs and was left out.`)
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
  const sequence = sequences.find(candidate => candidate.modifier_id === row.id)
  if (!sequence) {
    warnings.push(`${equipped.name}: chip affix ${row.id} is not in the current Builder Tower Sequence catalog and was left out.`)
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
      warnings.push(`${graft.name}: base attribute affix ${id} is not in the current Builder catalogs and was left out.`)
      continue
    }
    affixes.push({ ...mapped.affix, affix_kind: 'implicit', affix_type: 'Base' })
  }
  for (const id of item.baseAffixIds) {
    const mapped = toGraftAffix(id, null, graft, legendaryItems)
    if (!mapped) {
      warnings.push(`${graft.name}: base affix ${id} is not in the current Builder catalogs and was left out.`)
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
      warnings.push(`${name}: base attribute affix ${id} is not in the current Builder catalogs and was left out.`)
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
      warnings.push(`${name}: base affix ${id} is not in the current Builder catalogs and was left out.`)
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
        warnings.push(`${name}: affix ${row.id} could not be mapped and was left out.`)
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
  const variant = item.corroded
    ? unique.variants.corroded ?? unique.variants.base ?? Object.values(unique.variants)[0]
    : unique.variants.base ?? Object.values(unique.variants)[0]
  const affixes: LegendaryAffix[] = [...variant.implicits, ...variant.explicits]
  const customizations: NonNullable<Build['gear']>[number]['customizations'] = []
  const positions: number[] = []
  let legendarySource: string | null = null

  const applyRolls = (rows: UeLogGearItem['prefixes'], slotOffset: number) => {
    rows.forEach((row, index) => {
      if (!row.id) return
      let affixIndex = affixes.findIndex(candidate => candidate.modifier_id === row.id)
      if (affixIndex < 0) {
        const sameUnique = legendaryAffixes(unique).find(candidate => candidate.modifier_id === row.id)
        if (sameUnique) {
          affixIndex = affixes.length
          affixes.push({ ...sameUnique, affix_type: 'Legendary' })
        }
      }
      if (affixIndex < 0 && row.source === '17') {
        const mapped = byModifierId(legendaryItems, row.id)
        if (mapped) {
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
        warnings.push(`${unique.name}: affix ${row.id} could not be mapped and was left out.`)
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
      else warnings.push(`${unique.name}: base affix ${id} could not be mapped.`)
    }
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
        supportIndex: logIndex === rootIndex ? null : logIndex - rootIndex + 1,
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
      warnings.push(`Skill item ${row.baseId} at log slot ${row.logIndex} is not in a recognized skill slot.`)
      return []
    }
    const item = catalog.find(skill => skill.game_id === row.baseId && skill.game_id !== 0)
    if (!item) {
      warnings.push(`Skill item ${row.baseId} at log slot ${row.logIndex} is not in the current Builder skill catalog.`)
      return []
    }
    const isSupport = SUPPORT_SKILL_TYPES.has(item.skill_type ?? '') || item.skill_tags.includes('Support')
    return [{ row, position, item, isSupport }]
  })

  const roots = new Map<number, EquippedSkill>()
  for (const { row, position, item, isSupport } of mapped) {
    if (position.supportIndex !== null || isSupport) continue
    const level = row.level ?? 20
    if (row.level === null) warnings.push(`${item.name}: skill level was missing from the selected logs; Builder default level ${level} was used.`)
    roots.set(position.rootIndex, {
      slot: position.buildSlot,
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
      warnings.push(`${item.name}: support item was logged in a skill slot and was not attached.`)
      continue
    }
    const root = roots.get(position.rootIndex)
    if (!root) {
      warnings.push(`${item.name}: support at log slot ${row.logIndex} has no mapped parent skill.`)
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
    for (const prefix of row.prefixes) {
      if (prefix.id) warnings.push(`${item.name}: support modifier ${prefix.id} is not mapped; its roll and rank use Builder defaults.`)
    }
    if (RANKED_SUPPORT_TYPES.has(skillType) && row.prefixes.length === 0) {
      warnings.push(`${item.name}: support rank is not present in the log; Builder rank 1 was used.`)
    }
  }

  return [...roots.values()].map(skill => ({
    ...skill,
    supports: skill.supports.sort((a, b) => a.support_index - b.support_index),
  })).sort((a, b) => a.slot - b.slot)
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
): UeLogBuildResult {
  const warnings: string[] = []
  const gear: EquippedGearItem[] = []
  const unmappedBaseIds: number[] = []
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

    if (item.baseId !== null) unmappedBaseIds.push(item.baseId)
  }

  if (character.gear.length > gear.length) {
    warnings.unshift(`${character.gear.length - gear.length} of ${character.gear.length} equipped items are not mapped yet.`)
  }
  if (unmappedBaseIds.length > 0) {
    warnings.push(`Unmapped gear base IDs: ${unmappedBaseIds.join(', ')}.`)
  }
  const skills = buildLoggedSkills(character.skills ?? [], skillCatalog, warnings)
  const talentTreeAllocations = character.talentTreeAllocations ?? []
  if (talentTreeAllocations.length) {
    warnings.push(
      `Talent-tree allocation IDs (${talentTreeAllocations.map(row => row.id).join(', ')}) do not match the current TLIDB talent_id values; those allocations were not imported.`,
    )
  }
  const followerIds = [...new Set([
    character.followServantId,
    ...(character.servantIds ?? []),
  ].filter((id): id is number => id !== null && id !== undefined))]
  if (followerIds.length) {
    warnings.push(
      `Logged follower/servant IDs (${followerIds.join(', ')}) do not match current TLIDB follower game_id values; follower state was not imported.`,
    )
  }
  const truncatedSectionCount = character.truncatedSections?.length ?? 0
  if (truncatedSectionCount > 0) {
    warnings.push(
      `The selected login dump contains ${truncatedSectionCount} truncated data section${truncatedSectionCount === 1 ? '' : 's'}; values omitted by the game log could not be imported.`,
    )
  }
  warnings.unshift('Hero, talents, memories, and other character settings are not imported yet.')

  return {
    build: {
      name: `${character.characterName || `Hero ${character.heroId ?? 'unknown'}`} · Level ${character.level ?? 'unknown'}`,
      slots: [],
      gear,
      skills,
      characterLevel: character.level ?? 100,
      notes: 'Imported from UE_game.log. Review the import warnings and complete the missing character data.',
    },
    warnings,
  }
}
