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

export interface UeLogCharacterPreview {
  dumpNumber: number
  characterName: string | null
  level: number | null
  heroId: number | null
  heroPurchaseId: number | null
  gear: UeLogGearItem[]
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

function previewDump(body: string, dumpNumber: number): UeLogCharacterPreview {
  const tree = parseGetPlayerDataBody(body)
  const player = (tree.player ?? {}) as Record<string, unknown>
  const hero = (tree.heroCharacterv3OverView ?? {}) as Record<string, unknown>
  return {
    dumpNumber,
    characterName: typeof scalar(player.Name) === 'string' ? scalar(player.Name) as string : null,
    level: numberValue(scalar(player.Level)),
    heroId: numberValue(scalar(player.HeroId)),
    heroPurchaseId: numberValue(scalar(hero.heroPurchaseId)),
    gear: gearRows(tree),
    truncatedSections: [...body.matchAll(/^\s*\|*\s*\+\d+\+\.\.\./gm)].map(match => match[0].trim()),
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
