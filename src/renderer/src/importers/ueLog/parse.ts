const DUMP_START = 'RecvMessage STT----GetPlayerData'
const DUMP_END = '----Socket RecvMessage End----'
const MAX_DUMP_CHARS = 12_000_000

interface TreeNode {
  [key: string]: string | TreeNode | undefined
  __value?: string
}

export interface UeLogAffix {
  id: string | null
  source: string | null
  values: number[]
}

export interface UeLogGearItem {
  baseId: number | null
  itemLevel: number | null
  equippedSlot: number | null
  uniqueItemId: number | null
  baseAttrAffixIds: string[]
  baseAffixIds: string[]
  prefixes: UeLogAffix[]
  suffixes: UeLogAffix[]
  chipAffixes: UeLogAffix[]
  enchantAffixes: UeLogAffix[]
  corroded: boolean
}

export interface UeLogSkillItem {
  baseId: number
  logIndex: number
  level: number | null
  skillItemLevel: number | null
  prefixes: UeLogAffix[]
}

export interface UeLogMemory {
  slot: number | null
  baseId: number | null
  rarityValue: number | null
  level: number | null
  baseAttrAffixes: UeLogAffix[]
  fixedAffixes: UeLogAffix[]
  randomAffixes: UeLogAffix[]
  awakenAffixes: UeLogAffix[]
  rarityRequire?: number | null
  typeRequire?: number | null
  affixBoost?: number | null
}

export interface UeLogPactContract {
  areaId: number
  servantId: number
  rank: number | null
}

export interface UeLogIngredientChoice {
  bottleSlot: number
  materialSlot: number
  optionId: string
}

export interface UeLogSlate {
  index: number | null
  pageId: number | null
  baseId: number | null
  uniqueItemId: number | null
  shapeId: number | null
  direction: number | null
  rarityValue: number | null
  baseTalentIds: string[]
  enchantTalentIds: string[]
  talentSlots: Array<{ color: string | null; talentId: string | null; rarity: number | null; slotIndex?: number }>
}

export interface UeLogPrism {
  anchorTalentId: string | null
  baseId: number | null
  uniqueItemId: number | null
  rarityValue: number | null
  prefixAffixes: UeLogAffix[]
  baseAffixes: UeLogAffix[]
  baseAttrAffixes: UeLogAffix[]
  effectPositions: Array<{ x: number; y: number }>
  replacementTalentId: string | null
}

export interface UeLogCharacterPreview {
  dumpNumber: number
  characterName: string | null
  level: number | null
  heroId: number | null
  heroPurchaseId: number | null
  gear: UeLogGearItem[]
  skills: UeLogSkillItem[]
  talentTrees?: Array<{
    careerId: number | null
    allocations: Array<{ id: string; rank: number; inPrismArea?: boolean }>
    coreTalentSelections?: string[]
    prism?: UeLogPrism
  }>
  slates?: UeLogSlate[]
  followServantId?: number | null
  servantIds?: number[]
  activeTraitIds?: number[]
  memories?: UeLogMemory[]
  baseMemory?: UeLogMemory
  pactContracts?: UeLogPactContract[]
  ingredientChoices?: UeLogIngredientChoice[]
  truncatedSections: string[]
}

export interface UeLogScanResult {
  characters: UeLogCharacterPreview[]
  errors: string[]
}

function numberValue(value: unknown): number | null {
  if (typeof value !== 'string' || !value.trim()) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function entries(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  if (!value || typeof value !== 'object') return []
  return Object.keys(value as object)
    .filter(key => /^\d+$/.test(key))
    .sort((a, b) => Number(a) - Number(b))
    .map(key => (value as Record<string, unknown>)[key])
}

function indexedEntries(value: unknown): Array<[number, unknown]> {
  if (Array.isArray(value)) return value.map((entry, index) => [index, entry])
  if (!value || typeof value !== 'object') return []
  return Object.keys(value as object)
    .filter(key => /^\d+$/.test(key))
    .sort((a, b) => Number(a) - Number(b))
    .map(key => [Math.max(0, Number(key) - 1), (value as Record<string, unknown>)[key]])
}

function scalar(value: unknown): unknown {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const node = value as Record<string, unknown>
    return Object.keys(node).length === 1 && typeof node.__value === 'string' ? node.__value : value
  }
  return value
}

function materialize(node: TreeNode): unknown {
  const keys = Object.keys(node).filter(key => key !== '__value')
  if (keys.length === 0 && node.__value !== undefined) return node.__value

  const out: Record<string, unknown> = Object.create(null) as Record<string, unknown>
  if (node.__value !== undefined) out.__value = node.__value
  for (const key of keys) out[key] = materialize(node[key] as TreeNode)

  if (keys.length > 0 && keys.every(key => /^\d+$/.test(key))) {
    const sorted = [...keys].sort((a, b) => Number(a) - Number(b))
    if (sorted.every((key, index) => Number(key) === index + 1)) return sorted.map(key => out[key])
  }
  return out
}

/** Parse the bracket tree inside one GetPlayerData response. */
export function parseGetPlayerDataBody(body: string): Record<string, unknown> {
  const root: TreeNode = Object.create(null) as TreeNode
  const stack: Array<{ column: number; node: TreeNode }> = []

  for (const line of body.split(/\r?\n/)) {
    const plusAt = line.indexOf('+')
    if (plusAt < 0 || line.slice(0, plusAt).replace(/[|\s]/g, '') !== '') continue

    const segments: Array<{ column: number; key: string }> = []
    let cursor = plusAt
    while (line[cursor] === '+') {
      const next = line.indexOf('+', cursor + 1)
      const bracket = line.indexOf('[', cursor + 1)
      const end = next >= 0 && (bracket < 0 || next < bracket) ? next : (bracket >= 0 ? bracket : line.length)
      const key = line.slice(cursor + 1, end).trim()
      if (!key) break
      segments.push({ column: cursor, key })
      if (end === next) cursor = next
      else { cursor = end; break }
    }
    if (!segments.length) continue

    const remainder = line.slice(cursor).trim()
    const valueMatch = remainder.match(/^\[([\s\S]*)\]\s*$/)
    while (stack.length && stack[stack.length - 1].column >= segments[0].column) stack.pop()
    let parent = stack.length ? stack[stack.length - 1].node : root
    for (const segment of segments) {
      let child = parent[segment.key]
      if (!child || typeof child === 'string') {
        child = Object.create(null) as TreeNode
        parent[segment.key] = child
      }
      const childNode = child as TreeNode
      stack.push({ column: segment.column, node: childNode })
      parent = childNode
    }
    if (valueMatch) parent.__value = valueMatch[1]
  }

  return materialize(root) as Record<string, unknown>
}

function affixRows(value: unknown): UeLogAffix[] {
  return entries(value).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const row = raw as Record<string, unknown>
    const args = row.DynArgs && typeof row.DynArgs === 'object' ? row.DynArgs as Record<string, unknown> : {}
    const values = Object.keys(args)
      .filter(key => /^\d+$/.test(key))
      .sort((a, b) => Number(a) - Number(b))
      .map(key => numberValue(scalar(args[key])))
      .filter((n): n is number => n !== null)
    return [{ id: typeof scalar(row.Id) === 'string' ? scalar(row.Id) as string : null,
      source: typeof scalar(row.source) === 'string' ? scalar(row.source) as string : null, values }]
  })
}

function memoryRow(raw: unknown, slot: number | null, requirements?: Record<string, unknown>): UeLogMemory | null {
  if (!raw || typeof raw !== 'object') return null
  const entry = raw as Record<string, unknown>
  const detail = (entry.detail && typeof entry.detail === 'object' ? entry.detail : entry) as Record<string, unknown>
  return {
    slot,
    baseId: numberValue(scalar(detail.BaseId)),
    rarityValue: numberValue(scalar(detail.RareValue)),
    level: numberValue(scalar(detail.ReminiscenceLevel)),
    baseAttrAffixes: affixRows(detail.BaseAttrAffix),
    fixedAffixes: affixRows(detail.BaseAffix),
    randomAffixes: affixRows(detail.Suffix),
    awakenAffixes: affixRows(detail.AwakenAffix),
    ...(requirements ? {
      rarityRequire: numberValue(scalar(requirements.rarityRequire)),
      typeRequire: numberValue(scalar(requirements.typeRequire)),
      affixBoost: numberValue(scalar(requirements.affixBoost)),
    } : {}),
  }
}

function gearRows(tree: Record<string, unknown>): UeLogGearItem[] {
  const bag = tree.bag as Record<string, unknown> | undefined
  return entries(bag?.wearItems).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const record = raw as Record<string, unknown>
    const item = record.Item as Record<string, unknown> | undefined
    if (!item) return []
    return [{
      baseId: numberValue(scalar(item.BaseId)),
      itemLevel: numberValue(scalar(item.Level)),
      equippedSlot: numberValue(scalar(record.Index)),
      uniqueItemId: numberValue(scalar(item.UniqueItmId)),
      baseAttrAffixIds: entries(item.BaseAttrAffix).flatMap(row => {
        if (!row || typeof row !== 'object') return []
        const id = scalar((row as Record<string, unknown>).Id)
        return typeof id === 'string' ? [id] : []
      }),
      baseAffixIds: entries(item.BaseAffix).flatMap(row => {
        if (!row || typeof row !== 'object') return []
        const id = scalar((row as Record<string, unknown>).Id)
        return typeof id === 'string' ? [id] : []
      }),
      prefixes: affixRows(item.Prefix),
      suffixes: affixRows(item.Suffix),
      chipAffixes: affixRows(item.ChipAffix),
      enchantAffixes: affixRows(item.EnchantAffixs),
      corroded: scalar(item.Corrode) === 'true',
    }]
  })
}

function skillRows(tree: Record<string, unknown>): UeLogSkillItem[] {
  const bag = tree.bag as Record<string, unknown> | undefined
  const skillState = tree.skills as Record<string, unknown> | undefined
  const layout = tree.skillLayout as Record<string, unknown> | undefined
  const byItemId = new Map<string, {
    baseId: number
    logIndex: number | null
    level: number | null
    skillItemLevel: number | null
    prefixes: UeLogAffix[]
  }>()

  const add = (raw: unknown, logIndex: number | null) => {
    if (!raw || typeof raw !== 'object') return
    const item = raw as Record<string, unknown>
    const baseId = numberValue(scalar(item.BaseId))
    if (baseId === null) return
    const rawId = scalar(item.Id)
    const itemId = typeof rawId === 'string' ? rawId : `${baseId}:${logIndex ?? 'unplaced'}`
    const previous = byItemId.get(itemId)
    byItemId.set(itemId, {
      baseId,
      logIndex: logIndex ?? previous?.logIndex ?? null,
      level: numberValue(scalar(item.Level)) ?? previous?.level ?? null,
      skillItemLevel: numberValue(scalar(item.SkillItemLevel)) ?? previous?.skillItemLevel ?? null,
      prefixes: item.Prefix === undefined ? previous?.prefixes ?? [] : affixRows(item.Prefix),
    })
  }

  for (const raw of entries(bag?.dressSkillItems)) {
    if (!raw || typeof raw !== 'object') continue
    const row = raw as Record<string, unknown>
    if (scalar(row.PageId) !== '-6') continue
    add(row.Item, numberValue(scalar(row.Index)))
  }
  for (const raw of entries(skillState?.skills)) add(raw, null)

  const layoutIndexByItemId = new Map<string, number>()
  for (const raw of entries(layout?.slots)) {
    if (!raw || typeof raw !== 'object') continue
    const row = raw as Record<string, unknown>
    const logIndex = numberValue(scalar(row.key))
    const value = row.value as Record<string, unknown> | undefined
    const skillId = scalar(value?.skillId)
    if (logIndex !== null && typeof skillId === 'string') layoutIndexByItemId.set(skillId, logIndex)
  }

  for (const [itemId, row] of byItemId) {
    row.logIndex ??= layoutIndexByItemId.get(itemId) ?? null
  }
  // The slot map can identify an equipped skill whose detailed item record was one of the
  // entries omitted by TLIDB's 30-row response cap. Keep its game ID and slot; level/rolls
  // can be recovered from another login capture.
  for (const [itemId, logIndex] of layoutIndexByItemId) {
    if (byItemId.has(itemId)) continue
    const baseId = numberValue(itemId.split('_', 1)[0])
    if (baseId !== null) byItemId.set(itemId, { baseId, logIndex, level: null, skillItemLevel: null, prefixes: [] })
  }

  return [...byItemId.values()]
    .filter((row): row is typeof row & { logIndex: number } => row.logIndex !== null)
    .map(({ baseId, logIndex, level, skillItemLevel, prefixes }) => ({ baseId, logIndex, level, skillItemLevel, prefixes }))
    .sort((a, b) => a.logIndex - b.logIndex)
}

function loggedTalentTrees(tree: Record<string, unknown>): NonNullable<UeLogCharacterPreview['talentTrees']> {
  const geniusInfos = tree.geniusInfos as Record<string, unknown> | undefined
  return entries(geniusInfos?.info).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const info = raw as Record<string, unknown>
    const careerId = numberValue(scalar(info.geniusCareerId))
    const allocations = entries(info.geniusList).flatMap(entry => {
      if (!entry || typeof entry !== 'object') return []
      const row = entry as Record<string, unknown>
      const value = row.value && typeof row.value === 'object' ? row.value as Record<string, unknown> : {}
      const rawId = scalar(row.geniusId ?? row.key ?? value.geniusId)
      if (rawId === null || rawId === undefined) return []
      const id = String(rawId)
      const rank = ['rank', 'point', 'points', 'talentPoint', 'level', 'value']
        .map(key => numberValue(scalar(row[key] ?? value[key])))
        .find((n): n is number => n !== null && n > 0)
      if (rank === undefined) return []
      const inPrismArea = scalar(row.inPrismArea ?? value.inPrismArea) === 'true'
      return [{ id, rank, ...(inPrismArea ? { inPrismArea: true } : {}) }]
    })
    const coreTalentSelections = info.bonusGeniusInfo === undefined ? undefined : entries(info.bonusGeniusInfo).flatMap(entry => {
      if (!entry || typeof entry !== 'object') return []
      const row = entry as Record<string, unknown>
      const value = row.value && typeof row.value === 'object' ? row.value as Record<string, unknown> : {}
      if (scalar(value.isPrismSkill) === 'true') return []
      const rawId = scalar(row.geniusId ?? value.geniusId)
      return typeof rawId === 'string' ? [rawId] : []
    })
    const prismInfo = info.prismInfo && typeof info.prismInfo === 'object' ? info.prismInfo as Record<string, unknown> : null
    const prismItem = prismInfo?.item && typeof prismInfo.item === 'object' ? prismInfo.item as Record<string, unknown> : {}
    const rawAnchor = scalar(prismInfo?.geniusId)
    const rawReplacement = scalar(info.prismGeniusId)
    const prism = prismInfo ? {
      anchorTalentId: typeof rawAnchor === 'string' ? rawAnchor : null,
      baseId: numberValue(scalar(prismItem.BaseId)),
      uniqueItemId: numberValue(scalar(prismItem.UniqueItmId)),
      rarityValue: numberValue(scalar(prismItem.RareValue)),
      prefixAffixes: affixRows(prismItem.Prefix),
      baseAffixes: affixRows(prismItem.BaseAffix),
      baseAttrAffixes: affixRows(prismItem.BaseAttrAffix),
      effectPositions: entries(info.prismEffectPositions).flatMap(position => {
        if (!position || typeof position !== 'object') return []
        const row = position as Record<string, unknown>
        const x = numberValue(scalar(row.x)), y = numberValue(scalar(row.y))
        return x === null || y === null ? [] : [{ x, y }]
      }),
      replacementTalentId: typeof rawReplacement === 'string' ? rawReplacement : null,
    } : undefined
    return allocations.length || prism || coreTalentSelections?.length
      ? [{ careerId, allocations, ...(coreTalentSelections ? { coreTalentSelections } : {}), ...(prism ? { prism } : {}) }]
      : []
  })
}

function loggedSlates(tree: Record<string, unknown>): UeLogSlate[] {
  const bag = tree.bag as Record<string, unknown> | undefined
  return entries(bag?.dressingTalentBlocks).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const row = raw as Record<string, unknown>
    const item = row.Item && typeof row.Item === 'object' ? row.Item as Record<string, unknown> : {}
    const readIds = (value: unknown) => entries(value).map(scalar).filter((id): id is string => typeof id === 'string')
    return [{
      index: numberValue(scalar(row.Index)), pageId: numberValue(scalar(row.PageId)),
      baseId: numberValue(scalar(item.BaseId)), uniqueItemId: numberValue(scalar(item.UniqueItmId)),
      shapeId: numberValue(scalar(item.ShapeId)), direction: numberValue(scalar(item.Direction)),
      rarityValue: numberValue(scalar(item.RareValue)),
      baseTalentIds: readIds(item.BaseTalentList), enchantTalentIds: readIds(item.EnchantTalentList),
      talentSlots: indexedEntries(item.talentSlotList).flatMap(([slotIndex, slot]) => {
        if (!slot || typeof slot !== 'object') return []
        const value = slot as Record<string, unknown>
        const talentId = scalar(value.talentId)
        return [{ color: typeof scalar(value.color) === 'string' ? scalar(value.color) as string : null,
          talentId: typeof talentId === 'string' ? talentId : null, rarity: numberValue(scalar(value.rarity)), slotIndex }]
      }),
    }]
  })
}

function loggedIngredientChoices(tree: Record<string, unknown>): UeLogIngredientChoice[] {
  const custom = tree.customSkillSlots as Record<string, unknown> | undefined
  return entries(custom?.customSkillSlots).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const bottle = raw as Record<string, unknown>
    const bottleSlot = numberValue(scalar(bottle.id))
    if (bottleSlot === null) return []
    return entries(bottle.materialSlots).flatMap(materialRaw => {
      if (!materialRaw || typeof materialRaw !== 'object') return []
      const row = materialRaw as Record<string, unknown>
      const material = row.value && typeof row.value === 'object' ? row.value as Record<string, unknown> : row
      const materialSlot = numberValue(scalar(material.index)) ?? numberValue(scalar(row.key))
      const optionId = scalar(material.chooseOptionId)
      if (materialSlot === null || typeof optionId !== 'string' || !optionId) return []
      return [{ bottleSlot, materialSlot, optionId }]
    })
  })
}

function previewDump(body: string, dumpNumber: number): UeLogCharacterPreview {
  const tree = parseGetPlayerDataBody(body)
  const player = (tree.player ?? {}) as Record<string, unknown>
  const hero = (tree.heroCharacterv3OverView ?? {}) as Record<string, unknown>
  const servantInfos = tree.ServantInfos as Record<string, unknown> | undefined
  const ownedSpiritRanks = new Map<number, number>()
  for (const raw of entries(servantInfos?.servantData)) {
    if (!raw || typeof raw !== 'object') continue
    const servant = raw as Record<string, unknown>
    const servantId = numberValue(scalar(servant.servantId))
    if (servantId === null) continue
    const starLevel = numberValue(scalar(servant.starLevel))
    ownedSpiritRanks.set(servantId, starLevel === null ? 1 : Math.min(6, starLevel + 1))
  }
  const reminiscenceOverview = hero.reminiscenceOverView as Record<string, unknown> | undefined
  const memories = entries(reminiscenceOverview?.reminiscence).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const entry = raw as Record<string, unknown>
    const parsed = memoryRow(raw, numberValue(scalar(entry.index)))
    return parsed ? [parsed] : []
  })
  const baseMemory = memoryRow(hero.defaultReminis, null, hero.defaultReminis as Record<string, unknown> | undefined ?? undefined)
  const pointOverview = hero.pointOverView as Record<string, unknown> | undefined
  const activeTraitIds = entries(pointOverview?.activeId)
    .map(value => numberValue(scalar(value)))
    .filter((id): id is number => id !== null)
  const contracts = (tree.ContractInfosV2 as Record<string, unknown> | undefined)?.ContractDatas
  const pactContracts = entries(contracts).flatMap(raw => {
    if (!raw || typeof raw !== 'object') return []
    const contract = raw as Record<string, unknown>
    const areaId = numberValue(scalar(contract.areaId))
    const servantId = numberValue(scalar(contract.servantId))
    if (areaId === null || servantId === null) return []
    return [{ areaId, servantId, rank: ownedSpiritRanks.get(servantId) ?? null }]
  })
  const ingredientChoices = loggedIngredientChoices(tree)
  return {
    dumpNumber,
    characterName: typeof scalar(player.Name) === 'string' ? scalar(player.Name) as string : null,
    level: numberValue(scalar(player.Level)),
    heroId: numberValue(scalar(player.HeroId)),
    heroPurchaseId: numberValue(scalar(hero.heroPurchaseId)),
    gear: gearRows(tree),
    skills: skillRows(tree),
    talentTrees: loggedTalentTrees(tree),
    slates: loggedSlates(tree),
    followServantId: numberValue(scalar(player.FollowServant)),
    servantIds: entries(servantInfos?.servantData).flatMap(raw => {
      if (!raw || typeof raw !== 'object') return []
      const servantId = numberValue(scalar((raw as Record<string, unknown>).servantId))
      return servantId === null ? [] : [servantId]
    }),
    ...(activeTraitIds.length ? { activeTraitIds } : {}),
    ...(memories.length ? { memories } : {}),
    ...(baseMemory?.baseId !== null && baseMemory?.baseId !== undefined ? { baseMemory } : {}),
    ...(pactContracts.length ? { pactContracts } : {}),
    ...(ingredientChoices.length ? { ingredientChoices } : {}),
    truncatedSections: [...body.matchAll(/^[| ]*\+\d+\+\.\.\./gm)].map(match => match[0].trim()),
  }
}

/** Scan a file stream without retaining log text or account-identifying fields. */
export async function scanUeGameLog(file: File): Promise<UeLogScanResult> {
  const reader = file.stream().getReader()
  const decoder = new TextDecoder()
  const characters: UeLogCharacterPreview[] = []
  const errors: string[] = []
  let pending = ''
  let searching = true
  let dumpNumber = 0

  const consume = (chunk: string, final = false) => {
    pending += chunk
    while (true) {
      if (searching) {
        const start = pending.indexOf(DUMP_START)
        if (start < 0) {
          pending = final ? '' : pending.slice(-DUMP_START.length + 1)
          return
        }
        pending = pending.slice(start + DUMP_START.length)
        searching = false
      }
      const end = pending.indexOf(DUMP_END)
      if (end < 0) {
        if (pending.length > MAX_DUMP_CHARS) {
          errors.push(`Login dump ${dumpNumber + 1} is larger than the 12 MB safety limit.`)
          pending = pending.slice(-DUMP_START.length + 1)
          searching = true
          continue
        }
        if (final) errors.push(`Login dump ${dumpNumber + 1} is missing its end marker.`)
        return
      }
      const body = pending.slice(0, end)
      pending = pending.slice(end + DUMP_END.length)
      searching = true
      dumpNumber++
      try { characters.push(previewDump(body, dumpNumber)) }
      catch { errors.push(`Login dump ${dumpNumber} could not be parsed.`) }
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      consume(decoder.decode(value, { stream: true }))
    }
    consume(decoder.decode(), true)
  } finally {
    reader.releaseLock()
  }

  if (!characters.length && errors.length === 0) errors.push('No GetPlayerData login dumps were found in this file.')
  return { characters, errors }
}
