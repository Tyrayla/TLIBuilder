let BASE = ''
let ipcMode = false
export function getApiBase(): string { return BASE }

const verbose = typeof window !== 'undefined' && window.api?.isVerbose === true
const rlog = (...args: unknown[]) => { if (verbose) console.log('[api]', ...args) }
const rerr = (...args: unknown[]) => { if (verbose) console.error('[api]', ...args) }

async function probePort(port: number): Promise<boolean> {
  rlog(`probePort(${port}) — fetching /api/trees`)
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/trees`, {
      signal: AbortSignal.timeout(800),
    })
    rlog(`probePort(${port}) — status ${res.status}, ok=${res.ok}`)
    return res.ok
  } catch (e) {
    rlog(`probePort(${port}) — failed: ${e}`)
    return false
  }
}

export async function initApi(): Promise<void> {
  rlog('initApi — start, window.api defined:', typeof window !== 'undefined' && 'api' in window)
  if (window.api?.apiRequest) {
    ipcMode = true
    rlog('initApi — Electron IPC path: waiting for port readiness via getPythonPort')
    await window.api.getPythonPort()
    rlog('initApi — IPC ready, ipcMode=true')
    return
  }
  rlog('initApi — browser path: scanning ports 8765-8774')
  for (let port = 8765; port <= 8774; port++) {
    if (await probePort(port)) {
      BASE = `http://127.0.0.1:${port}/api`
      rlog(`initApi — found server on port ${port}, BASE: ${BASE}`)
      return
    }
  }
  BASE = 'http://127.0.0.1:8765/api'
  rerr(`initApi — no server found on 8765-8774, defaulting BASE to: ${BASE}`)
}

async function get<T>(path: string, retries = 4): Promise<T> {
  if (ipcMode) {
    rlog(`GET (IPC) ${path}`)
    const result = await window.api!.apiRequest('GET', path) as { ok: boolean; status: number; data: T }
    if (!result.ok) throw new Error(`GET ${path} → ${result.status}`)
    return result.data
  }
  const url = `${BASE}${path}`
  for (let attempt = 0; attempt <= retries; attempt++) {
    rlog(`GET ${url} — attempt ${attempt + 1}/${retries + 1}`)
    try {
      const res = await fetch(url)
      rlog(`GET ${url} — status ${res.status}`)
      if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
      return await res.json()
    } catch (e) {
      const isNetwork = e instanceof TypeError
      rerr(`GET ${url} — error (isNetwork=${isNetwork}): ${e}`)
      if (!isNetwork || attempt === retries) throw e
      const delay = 400 * (attempt + 1)
      rlog(`GET ${url} — retrying in ${delay}ms`)
      await new Promise(r => setTimeout(r, delay))
    }
  }
  throw new Error(`GET ${path} failed`)
}

async function post<T>(path: string, body: unknown): Promise<T> {
  if (ipcMode) {
    rlog(`POST (IPC) ${path}`)
    const result = await window.api!.apiRequest('POST', path, body) as { ok: boolean; status: number; data: T }
    if (!result.ok) throw new Error(`POST ${path} → ${result.status}`)
    return result.data
  }
  const url = `${BASE}${path}`
  rlog(`POST ${url}`)
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
  rlog(`POST ${url} — status ${res.status}`)
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json()
}

async function put<T>(path: string, body: unknown): Promise<T> {
  if (ipcMode) {
    rlog(`PUT (IPC) ${path}`)
    const result = await window.api!.apiRequest('PUT', path, body) as { ok: boolean; status: number; data: T }
    if (!result.ok) throw new Error(`PUT ${path} → ${result.status}`)
    return result.data
  }
  const url = `${BASE}${path}`
  rlog(`PUT ${url}`)
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
  rlog(`PUT ${url} — status ${res.status}`)
  if (!res.ok) throw new Error(`PUT ${path} → ${res.status}`)
  return res.json()
}

async function del<T>(path: string, body?: unknown): Promise<T> {
  if (ipcMode) {
    rlog(`DELETE (IPC) ${path}`)
    const result = await window.api!.apiRequest('DELETE', path, body) as { ok: boolean; status: number; data: T }
    if (!result.ok) throw new Error(`DELETE ${path} → ${result.status}`)
    return result.data
  }
  const url = `${BASE}${path}`
  rlog(`DELETE ${url}`)
  const res = await fetch(url, {
    method: 'DELETE',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  rlog(`DELETE ${url} — status ${res.status}`)
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`)
  return res.json()
}

// ── Share service ────────────────────────────────────────────────────────────
// The build-code share service is a PUBLIC host, separate from the local Python
// backend. Share calls never go through the local backend or Electron IPC —
// they are plain fetches to SHARE_BASE. The base URL is configurable at build
// time via the Vite env var VITE_SHARE_BASE_URL; it falls back to production.

const _shareEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
const SHARE_BASE = (_shareEnv?.VITE_SHARE_BASE_URL ?? 'https://api.tlibuilder.com').replace(/\/+$/, '')

export function getShareBase(): string { return SHARE_BASE }

async function postToShareService<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${SHARE_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

const MAX_SHARE_CODE_BYTES = 512 * 1024 // 512 KB — more than enough for any build code

async function getFromShareService(path: string): Promise<string> {
  // The share service returns the raw tli1_ code as text/plain.
  const res = await fetch(`${SHARE_BASE}${path}`, {
    signal: AbortSignal.timeout(15000),
  })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  const len = Number(res.headers.get('content-length') ?? 0)
  if (len > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
  // No Content-Length fallback: buffers entire response before rejecting — acceptable
  // given threat model; a streaming reader would be needed to truly bound a hostile server.
  const text = await res.text()
  if (text.length > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
  return text
}

export interface TreeSlot {
  treeName: string
  nodeStates: Record<string, number>
  coreTalentSelections?: Record<string, string>  // slot index → selected talent id
}

export interface SavedSlateSlot {
  slotType: 'magic' | 'rare' | 'legendary'
  maxType: 'magic' | 'rare' | 'legendary'
  canBeCore: boolean
  isCore: boolean
  selectedNodeId: string | null
  selectedCoreKey: string | null
  coreName: string | null
  effects: string[]
}

export interface SavedSlate {
  id: string
  kind: string
  cells: [number, number][]
  orientationIndex: number
  shapeIndex: number
  anchor: [number, number]
  slots: SavedSlateSlot[]
  treeType?: string
  mothDirection?: string
}

export interface Build {
  id?: string
  name: string
  slots: (TreeSlot | null)[]
  slates?: SavedSlate[]
  conditionState?: Record<string, number | boolean>
  // Legacy fields — present on builds saved before the conditionState unification.
  // Read-only: never written by the current client; migrated to conditionState on load.
  conditions?: string[]
  conditionValues?: Record<string, number>
  gear?: EquippedGearItem[]
  skills?: EquippedSkill[]
  characterLevel?: number
  hasPrism?: boolean
  traitId?: string | null
  traitLevel?: number          // legacy field — kept for loading old saves
  traitSlotLevels?: number[]   // [base, lv45, lv60, lv75], each 1–5
  advancedTraitSelections?: string[]
  heroMemories?: (unknown | null)[]
  pactSpirits?: (unknown | null)[]
  notes?: string
}

export interface TreeNode {
  id: string
  column: number
  row: number
  max_points: number
  node_type: string
  current_points: number
  effects: string[]
}

export interface CoreTalentSlotOption {
  id: string
  name: string
  effects: string[]
}

export interface CoreTalentSlot {
  threshold: number
  options: CoreTalentSlotOption[]
  selected_id: string | null
}

export interface TreeData {
  name: string
  nodes: TreeNode[]
  connections: { from: string; to: string }[]
  core_talent_slots: CoreTalentSlot[]
  node_prefix: string
}

export interface NodeEditData {
  id: string
  column: number
  row: number
  node_type: string
  max_points: number
}

export interface ModPoolEntry {
  stat: string
  display_name: string
  unit: string
  micro_increment: number
  medium_increment: number
  legendary_increment: number
  node_types: string[]
}

export interface SnapshotModifier {
  text: string
}

export interface StatRecipe {
  stat: string
  rank1: number
  values: number[]
  display_name: string
}

export interface TiedCandidate {
  stat: string
  display_name: string
  score: number
}

export interface UnresolvedStat {
  tree: string
  node_type: string
  text: string
  reason?: 'ambiguous' | 'unmatched' | 'multi_text' | 'conditional'
  tied?: TiedCandidate[]
}

export interface SnapshotStatus {
  exists: boolean
  source_file: string | null
  generated_at: string | null
}

export interface NodeTypeFilterMeta {
  generated_at: string
  snapshot_source: string
  matched: number
  ambiguous: number
  unmatched: number
  conditional: number
}

export interface FilterOverride {
  stat: string
  example: string
}

export interface RebuildFilterResult {
  _meta: NodeTypeFilterMeta
  stats: Record<string, string[]>
  unresolved: UnresolvedStat[]
  matched_texts: Record<string, string[]>
}

export interface TalentStat {
  text: string
  max_divinity_effect?: true
}

export interface TalentNode {
  node_type: string
  stats: TalentStat[]
}

export interface CoreTalentEntry {
  name: string
  stats: TalentStat[]
}

export interface NewGodTalent {
  name: string
  stats: TalentStat[]
}

export interface TreeSnapshot {
  nodes: TalentNode[]
  core_talents: CoreTalentEntry[]
}

export interface TalentSnapshot {
  generated_at: string
  source_file: string
  trees: Record<string, TreeSnapshot>
  new_god_talents: NewGodTalent[]
}

export interface SlateModifierOption {
  nodeId: string
  treeName: string
  nodeType: string
  effects: string[]
}

export interface CoreTalentOption {
  key: string       // "{treeName}:{display_name_key}"
  treeName: string
  name: string
  effects: string[]
}

export interface SlatePool {
  magic: SlateModifierOption[]
  rare: SlateModifierOption[]
  legendary: SlateModifierOption[]
  core: CoreTalentOption[]
}

export interface ConditionDef {
  key: string
  label: string
  category?: string
  value_type: 'boolean' | 'numeric'
  numeric_min?: number
  numeric_max?: number | null
  min_base?: number
  min_from_stat?: string | null
  max_base?: number
  max_from_stat?: string | null
  unit?: string
  default_value?: number
  default_bool?: boolean
  visible?: boolean
  is_derived?: boolean
  source?: string
}

export interface ConditionSourceEntry {
  text: string
  sources: string[]
  affix_count: number
  expression: Record<string, unknown> | string | null
  mapped: boolean
}

export interface ConditionDefsResponse {
  conditions: ConditionDef[]
  derived_keys: Record<string, string>
}

export interface StatSource {
  source_type: string
  label: string
  text: string
  amount: number
  points: number  // allocated points; >1 for multi-rank talent nodes
}

export interface StatEntry {
  display_name: string
  category: string
  unit: string    // "" | "%"
  total: number
  sources: StatSource[]
}

export interface StatSheetResponse {
  stats: Record<string, StatEntry>
  condition_maximums: Record<string, number>
  clamp_report: Record<string, { requested: number; applied: number }>
}

export const EMPTY_STAT_SHEET: StatSheetResponse = {
  stats: {},
  condition_maximums: {},
  clamp_report: {},
}

export type DiffStatus = 'added' | 'removed' | 'changed' | 'unchanged'

export interface DiffNode {
  index: number
  node_type: string
  status: DiffStatus
  stats_a: TalentStat[] | null
  stats_b: TalentStat[] | null
}

export interface DiffNamedTalent {
  name: string
  status: DiffStatus
  stats_a: TalentStat[] | null
  stats_b: TalentStat[] | null
}

export interface DiffTree {
  status: DiffStatus
  nodes: DiffNode[]
  core_talents: DiffNamedTalent[]
}

export interface TalentDiff {
  summary: {
    trees_added: number; trees_removed: number
    nodes_added: number; nodes_removed: number; nodes_changed: number
    core_talents_added: number; core_talents_removed: number; core_talents_changed: number
    new_god_added: number; new_god_removed: number; new_god_changed: number
  }
  trees: Record<string, DiffTree>
  new_god_talents: DiffNamedTalent[]
}

export interface SeasonSummary {
  name: string
  trees: string[]
  node_counts: Record<string, number>
  new_god_count: number | null
  legendary_gear_count: number | null
  skill_count: number | null
  hero_trait_count: number | null
  pact_spirit_count: number | null
  craft_base_type_count: number | null
  graft_count: number | null
  destiny_count: number | null
  ethereal_prism_count: number | null
  hero_memories_count: number | null
  memory_revival_count: number | null
  tower_sequence_count: number | null
  is_active: boolean
}

export interface HeroTraitLevel {
  level: number
  effects: string[]
  unlock_level: number
}

export interface HeroAdvancedTrait {
  name: string
  unlock_level: number          // 45 | 60 | 75
  is_pick_one_from_two: boolean
  effects: string[]
}

export interface HeroTrait {
  trait_id: string
  hero: string
  variant_name: string
  description: string
  levels: HeroTraitLevel[]
  artificial_moon: { description: string; effects: string[] }
  advanced_traits: HeroAdvancedTrait[]
  max_level?: number | null
  glossary?: Record<string, { name: string; description: string }>
}

export interface PactSpiritSlot {
  name: string
  effect: string
  ring: 'inner' | 'mid' | 'outer'
}

export interface PactSpiritRank {
  rank: number
  modifiers: string[]
}

export interface PactSpirit {
  item_id: string
  name: string
  description: string
  affinities: string[]
  main_skill_name: string
  main_skill_effect: string
  upgrade_ranks: PactSpiritRank[]
  slots: PactSpiritSlot[]
  glossary: Record<string, { name: string; description: string }>
}

export interface SelectedPactSpirit {
  itemId: string
  rank: number  // 1–6
}

export function buildSpiritEffects(
  selected: (SelectedPactSpirit | null)[],
  allSpirits: PactSpirit[]
): string[] {
  const effects: string[] = []
  for (const sel of selected) {
    if (!sel) continue
    const spirit = allSpirits.find(s => s.item_id === sel.itemId)
    if (!spirit) continue
    // Inner/mid effects are static; outer effects scale with rank and live in rankData.modifiers
    for (const slot of spirit.slots) {
      if (slot.ring !== 'outer') effects.push(slot.effect)
    }
    const rankData = spirit.upgrade_ranks.find(r => r.rank === sel.rank)
    if (rankData) effects.push(...rankData.modifiers)
  }
  return effects
}

export interface DualStatGroup {
  value_index: number
  stat_keys: string[]
  unit?: string
}

export interface ResolvedAffixFields {
  stat_key?: string | null
  unit?: string
  stat_keys?: string[]
  is_range_split?: boolean
  min_stat_keys?: string[]
  max_stat_keys?: string[]
  dual_stat_groups?: DualStatGroup[]
}

export interface CraftAffix {
  raw_text: string
  expression: string
  condition: string | null
  affix_kind: 'numeric' | 'special' | 'placeholder'
  numeric_values: LegendaryNumericValue[]
  source: string
  affix_type: string
  tier: string
  stat_key?: string | null
  stat_keys?: string[]
  is_range_split?: boolean
  min_stat_keys?: string[]
  max_stat_keys?: string[]
  dual_stat_groups?: DualStatGroup[]
  unit?: string
}

export interface CraftBaseItem {
  name: string
  required_level: number
  armor: string | null
  implicits: string[]  // base item implicit stats (from crawler when available)
}

export interface CraftBaseType {
  item_id: string
  name: string
  affixes: CraftAffix[]
  base_items: CraftBaseItem[]
  corrosion_base_affixes?: Array<LegendaryAffix & { modifier_text: string }>
}

// Lightweight version — no affix pools, just base item metadata
export interface CraftBaseItemGroup {
  item_id: string
  name: string
  base_items: CraftBaseItem[]
}

export interface GraftAffix {
  raw_text: string
  expression: string
  condition: string | null
  affix_kind: 'numeric' | 'special' | 'placeholder'
  numeric_values: LegendaryNumericValue[]
  tier: string
  level: number
  weight: number
  affix_type: string
}

export interface Graft {
  item_id: string
  name: string
  legendary_items: string[]
  base_affixes: GraftAffix[]
  affixes: GraftAffix[]
}

export interface DestinyItem {
  name: string
  text: string
}

export interface HeroMemoryAffix {
  tier: number
  modifier: string
  level: number
  weight: number
  source: string
}

export interface HeroMemoryType {
  name: string
  internal_id: number | null
  icon_url: string
}

export type MemoryRarity = 'normal' | 'magic' | 'rare' | 'epic' | 'ultimate'

export const MEMORY_RARITY_COLORS: Record<MemoryRarity, string> = {
  normal:   '#e0e0e0',
  magic:    '#4fc3f7',
  rare:     '#ce93d8',
  epic:     '#ffa726',
  ultimate: '#ef5350',
}

export interface MemorySlotSelection {
  modifier: string
  tier: number
  rolledValue: number | null
}

export interface CreatedHeroMemory {
  memoryType: 'origin' | 'discipline' | 'progress'
  rarity: MemoryRarity
  baseStat: MemorySlotSelection | null
  fixedAffixes: [MemorySlotSelection | null, MemorySlotSelection | null]
  randomAffixes: [MemorySlotSelection | null, MemorySlotSelection | null]
}

export function buildMemoryEffects(memories: (CreatedHeroMemory | null)[]): string[] {
  const effects: string[] = []
  const RANGE_RE = /\(\d+(?:\.\d+)?[–\-]\d+(?:\.\d+)?\)/g
  const resolveModifier = (sel: MemorySlotSelection): string => {
    // Ensure leading + for modifiers stored without it (handles legacy/missing-plus data)
    const mod = /^\d/.test(sel.modifier) ? '+' + sel.modifier : sel.modifier
    if (sel.rolledValue === null) return mod
    const val = Number.isInteger(sel.rolledValue) ? String(sel.rolledValue) : sel.rolledValue.toFixed(1)
    return mod.replace(RANGE_RE, val)
  }
  for (const mem of memories) {
    if (!mem) continue
    if (mem.baseStat) effects.push(resolveModifier(mem.baseStat))
    for (const fa of mem.fixedAffixes) { if (fa) effects.push(resolveModifier(fa)) }
    for (const ra of mem.randomAffixes) { if (ra) effects.push(resolveModifier(ra)) }
  }
  return effects
}

export interface MemoryRevivalAffix {
  tier: number
  modifier: string
  level: number
  weight: number
}

export interface TowerSequenceEntry {
  affix: string
  source: string
}

export interface SkillItem {
  item_id: string
  name: string
  internal_id?: number | null
  skill_type?: string
  description_lines: string[]
  raw_text: string
  skill_tags: string[]
  max_level?: number | null
  mana_cost?: string | null
  cast_speed?: string | null
  weapon_restriction?: string | null
  main_stat?: string | null
  progression?: object[]
  glossary?: Record<string, { name: string; description: string }>
}

export interface EquippedSupportSkill {
  support_index: number   // 1-5
  item_id: string
  name: string
  skill_type: string
  level: number
  skill_tags: string[]
  description_lines: string[]
}

export interface EquippedSkill {
  slot: number            // 1-5 = active; 6-9 = passive
  item_id: string
  name: string
  level: number           // 20 = base; 21-30 = +10%/level; 31+ = +8%/level
  skill_tags: string[]
  description_lines: string[]
  supports: EquippedSupportSkill[]
}

const PASSIVE_TAGS = new Set(['Aura', 'Spirit Magus', 'Focus'])

export function isPassiveSkillItem(s: SkillItem): boolean {
  return s.skill_tags.some(t => PASSIVE_TAGS.has(t))
}

export function isActiveSkillItem(s: SkillItem): boolean {
  return !isPassiveSkillItem(s) &&
    !s.skill_tags.includes('Support') &&
    !s.description_lines[0]?.startsWith('Supports') &&
    !s.name.includes(':')
}

// Compound tag aliases: support text spelling → canonical skill tag
const TAG_ALIASES: Record<string, string> = {
  'Slash Strike': 'Slash-Strike',
}

function parseRequiredTags(phrase: string): string[] {
  let remaining = phrase
  const tags: string[] = []
  const sortedAliases = Object.keys(TAG_ALIASES).sort((a, b) => b.length - a.length)
  while (remaining.length > 0) {
    let matched = false
    for (const alias of sortedAliases) {
      if (remaining.toLowerCase().startsWith(alias.toLowerCase())) {
        tags.push(TAG_ALIASES[alias])
        remaining = remaining.slice(alias.length).trim()
        matched = true
        break
      }
    }
    if (!matched) {
      const m = remaining.match(/^(\S+)\s*(.*)$/)
      if (m) { tags.push(m[1]); remaining = m[2] }
      else break
    }
  }
  return tags
}

function checkTag(tag: string, skillTags: string[], isPassiveSlot: boolean): boolean {
  if (tag.toLowerCase() === 'active') return !isPassiveSlot
  if (tag.toLowerCase() === 'passive') return isPassiveSlot
  return skillTags.some(t => t.toLowerCase() === tag.toLowerCase())
}

export function isSupportCompatible(
  support: SkillItem,
  parentSkill: EquippedSkill,
  isPassiveSlot: boolean,
  supportIdx: number
): boolean {
  // Tag-based exclusion: certain support tags require the parent to share that tag
  if (support.skill_tags.includes('Spirit Magus') && !parentSkill.skill_tags.includes('Spirit Magus')) return false
  if (support.skill_tags.includes('Summon') && !parentSkill.skill_tags.includes('Summon')) return false
  if (support.skill_tags.includes('Spell') && !support.skill_tags.includes('Attack') &&
      !parentSkill.skill_tags.includes('Spell')) return false
  if (support.skill_tags.includes('Attack') && !support.skill_tags.includes('Spell') &&
      !parentSkill.skill_tags.includes('Attack')) return false

  // Activation Medium: any active skill, slot 1 only (checked before description guard)
  if (support.skill_tags.includes('Activation Medium')) {
    return !isPassiveSlot && supportIdx === 1
  }

  // Colon = skill-specific support (Magnificent → slot 3, Noble → slot 5)
  if (support.name.includes(':')) {
    const parentPart = support.name.split(':')[0].trim()
    if (parentSkill.name !== parentPart) return false
    const ordinals: [string, number][] = [
      ['first', 1], ['second', 2], ['third', 3], ['fourth', 4], ['fifth', 5],
    ]
    for (const descLine of support.description_lines) {
      if (descLine.includes('Support Skill Slot')) {
        for (const [word, num] of ordinals) {
          if (descLine.toLowerCase().includes(word)) return num === supportIdx
        }
      }
    }
    return true
  }

  // Generic "Supports X Skills" description parsing
  const firstLine = support.description_lines[0] || ''
  if (!firstLine.startsWith('Supports')) return false

  const raw = firstLine.replace(/^Supports\s+/, '').replace(/\.\s*$/, '').trim()
  if (raw.toLowerCase() === 'any skill' || raw.toLowerCase() === 'any skills') return true
  if (/^skills?\s+that/i.test(raw)) return true

  const alternatives = raw.split(/\s+or\s+/i)
  return alternatives.some(alt => {
    const andGroups = alt.split(/\s+and\s+/i)
    return andGroups.every(group => {
      const phrase = group.replace(/\s+skills?\s*$/i, '').trim()
      const required = parseRequiredTags(phrase)
      return required.every(tag => checkTag(tag, parentSkill.skill_tags, isPassiveSlot))
    })
  })
}

// Support slot energy costs (index 1-5 within each skill)
const SUPPORT_ACTIVE_COSTS  = [0, 10, 15, 50, 100]
const SUPPORT_PASSIVE_COSTS = [10, 10, 15, 50, 100]

export function getSupportEnergyCost(isPassive: boolean, supportIdx: number): number {
  const costs = isPassive ? SUPPORT_PASSIVE_COSTS : SUPPORT_ACTIVE_COSTS
  return costs[Math.max(0, Math.min(4, supportIdx - 1))]
}

// Per-gear-slot energy contribution (helm/gloves/boots/each 1H = 61; chest/2H = 122)
function gearSlotEnergy(slot: GearSlot | GearSlot[] | null): number {
  if (!slot) return 0
  if (Array.isArray(slot)) return slot.reduce((s, sl) => s + gearSlotEnergy(sl), 0)
  if (slot === 'chest') return 122
  if (slot === 'weapon1' || slot === 'weapon2') return 61  // refined when base_type known
  if (slot === 'helmet' || slot === 'gloves' || slot === 'boots') return 61
  return 0  // amulet, belt, ring1, ring2
}

export function getMaxEnergy(level: number, gear: EquippedGearItem[], hasPrism: boolean): number {
  const fromGear = gear.reduce((s, g) => s + gearSlotEnergy(g.slot), 0)
  return 4 + fromGear + Math.min(Math.max(level, 0), 100) + (hasPrism ? 1000 : 0)
}

export interface CharacterStatContribution {
  stat: string
  amount: number
  label: string
  text: string
}

export function buildEnergyContributions(
  gear: EquippedGearItem[],
  characterLevel: number,
  hasPrism: boolean,
): CharacterStatContribution[] {
  const contribs: CharacterStatContribution[] = []
  contribs.push({ stat: 'max_energy_flat', amount: 4, label: 'Base', text: '+4 Max Energy' })
  const gearE = gear.reduce((s, g) => s + gearSlotEnergy(g.slot), 0)
  if (gearE > 0) contribs.push({ stat: 'max_energy_flat', amount: gearE, label: 'Gear', text: `+${gearE} Max Energy` })
  const lvlE = Math.min(Math.max(characterLevel, 0), 100)
  if (lvlE > 0) contribs.push({ stat: 'max_energy_flat', amount: lvlE, label: 'Levels', text: `+${lvlE} Max Energy` })
  if (hasPrism) contribs.push({ stat: 'max_energy_flat', amount: 1000, label: 'Prism', text: '+1000 Max Energy (Effortless Command)' })
  return contribs
}

export interface LegendaryNumericValue {
  kind: 'range' | 'fixed'
  sign: string | null
  // range
  min?: number
  max?: number
  // fixed
  value?: number
  raw: string
}

export interface LegendaryAffix {
  raw_text: string
  modifier_id: string | null
  expression: string
  condition: string | null
  affix_kind: 'numeric' | 'special' | 'tagged' | 'placeholder' | 'implicit'
  numeric_values: LegendaryNumericValue[]
  // resolved by backend at load time
  stat_key?: string | null
  stat_keys?: string[]
  is_range_split?: boolean
  min_stat_keys?: string[]
  max_stat_keys?: string[]
  dual_stat_groups?: DualStatGroup[]
  unit?: string
  // set for crafted/vorax items: 'Base' | 'Basic Affix' | 'Advanced Affix' | 'Ultimate Affix' | 'Legendary'
  affix_type?: string
  // resolved by backend: structured engine expression if condition text was mapped
  condition_expr?: Record<string, unknown> | string | null
}

export interface LegendaryGearVariant {
  implicits: LegendaryAffix[]
  explicits: LegendaryAffix[]
}

export interface LegendaryRandomAffixGroup {
  placeholder: string
  options: LegendaryAffix[]
}

export interface LegendaryGearIndexItem {
  item_id: string
  name: string
  required_level: number
  base_type: string
}

export interface LegendaryGearItem {
  item_id: string
  name: string
  internal_id: number | null
  base_type: string
  required_level: number
  drop_level: number | null
  flavor_text: string | null
  drop_sources: string[]
  glossary: Record<string, { name: string; description: string }>
  variants: Record<string, LegendaryGearVariant>
  random_affixes: Record<string, LegendaryRandomAffixGroup[]>
}

export type GearSlot = 'helmet' | 'amulet' | 'chest' | 'gloves' | 'belt'
                     | 'boots' | 'ring1' | 'ring2' | 'weapon1' | 'weapon2'

export interface CustomizedAffix {
  affix_index: number
  chosen_values: Record<number, number>   // value_index → chosen number
  chosen_placeholder_key: string | null
}

export interface EquippedGearItem {
  item_id: string
  name: string
  required_level: number
  affixes: LegendaryAffix[]
  customizations: CustomizedAffix[]
  slot: GearSlot | GearSlot[] | null
  base_type?: string
  is_crafted?: boolean
  is_vorax?: boolean
  legendary_source?: string | null
  legendary_affix_count?: number
  base_stats?: Record<string, number>
  implicit_count?: number
  craft_slot_positions?: number[]
  corrosion_type?: 'none' | 'desecration' | 'mutation'
  corroded_explicit_indices?: number[]
  mutation_affix_text?: string | null
  mutation_resolved_affix?: LegendaryAffix | null
  selected_random_affixes?: Record<number, string>
}

export interface GearAffixContribution {
  stat: string
  display_value: number
  unit: string
  item_name: string
  slot: string | null
  condition?: Record<string, unknown> | string | null
}

export interface GearEngineItem {
  contributions: GearAffixContribution[]
}

export interface SeasonDiffNode {
  id: string
  node_type: string
  max_points: number
  effects: string[]
}

export interface SeasonDiffNodeChange {
  id: string
  old: SeasonDiffNode | null
  new: SeasonDiffNode | null
}

export interface SeasonDiffTree {
  status: 'added' | 'removed' | 'changed' | 'unchanged'
  nodes_added: SeasonDiffNode[]
  nodes_removed: SeasonDiffNode[]
  nodes_changed: SeasonDiffNodeChange[]
  connections_added: { from: string; to: string }[]
  connections_removed: { from: string; to: string }[]
}

export interface ImportCrawlerTreeResult {
  ok: boolean
  tree_name: string
  node_count?: number
  core_talent_count?: number
  connection_count?: number
  count?: number
}

export interface SeasonDiff {
  summary: {
    trees_added: number
    trees_removed: number
    nodes_added: number
    nodes_removed: number
    nodes_changed: number
    connections_added: number
    connections_removed: number
  }
  trees: Record<string, SeasonDiffTree>
}

export const api = {
  getTrees: () => get<{ name: string; color: string }[]>('/trees'),

  getTree: (name: string) => get<TreeData>(`/tree/${encodeURIComponent(name)}`),

  getBuilds: () => get<Build[]>('/builds'),
  postBuild: (build: { id?: string; name: string; slots: (TreeSlot | null)[]; slates?: SavedSlate[]; conditionState?: Record<string, number | boolean> }) =>
    post<Build>('/builds', build),
  deleteBuild: (id: string) => del<{ ok: boolean }>(`/builds/${id}`),

  encodeBuildCode: (build: object) =>
    post<{ code: string }>('/build-code/encode', { build }),
  decodeBuildCode: (code: string) =>
    post<{ build: Record<string, unknown> }>('/build-code/decode', { code }),

  // Share service — store/fetch a build code by short id (public host).
  shareBuildCode: (code: string) =>
    postToShareService<{ id: string; url: string }>('/b', { code }),
  fetchSharedBuildCode: (id: string) =>
    getFromShareService(`/b/${id}`),

  // Tree editing (debug tools)
  upsertNode: (tree: string, node: NodeEditData) =>
    post<{ ok: boolean }>(`/tree/${encodeURIComponent(tree)}/node`, node),
  removeNode: (tree: string, nodeId: string) =>
    del<{ ok: boolean }>(`/tree/${encodeURIComponent(tree)}/node/${encodeURIComponent(nodeId)}`),
  toggleConnection: (tree: string, src: string, dst: string) =>
    post<{ ok: boolean }>(`/tree/${encodeURIComponent(tree)}/connection`, { src, dst }),

  getModifierPool: () => get<ModPoolEntry[]>('/modifier-pool'),

  // Dev tools
  parseTalentDoc: async (file: File): Promise<TalentSnapshot> => {
    if (ipcMode) {
      rlog('parseTalentDoc (IPC) — reading file bytes')
      const bytes = new Uint8Array(await file.arrayBuffer())
      const result = await window.api!.apiFormUpload('/dev/parse-talent-doc', bytes, file.name) as { ok: boolean; status: number; data: TalentSnapshot }
      if (!result.ok) return Promise.reject(result.data ?? 'Upload failed')
      return result.data
    }
    const form = new FormData()
    form.append('file', file)
    const r = await fetch(`${BASE}/dev/parse-talent-doc`, { method: 'POST', body: form })
    if (!r.ok) return Promise.reject((await r.json()).detail ?? r.statusText)
    return r.json()
  },
  diffSnapshots: (a: TalentSnapshot, b: TalentSnapshot): Promise<TalentDiff> =>
    post<TalentDiff>('/dev/diff-snapshots', { snapshot_a: a, snapshot_b: b }),

  saveCanonicalSnapshot: (snapshot: TalentSnapshot): Promise<{ ok: boolean; source_file: string; generated_at: string }> =>
    post<{ ok: boolean; source_file: string; generated_at: string }>('/dev/save-snapshot', { snapshot }),
  getSnapshotStatus: () => get<SnapshotStatus>('/dev/snapshot-status'),
  rebuildNodeTypeFilter: () => post<RebuildFilterResult>('/dev/rebuild-node-type-filter', {}),
  exportStatMeta: () => post<{ ok: boolean; stat_count: number; path: string }>('/dev/export-stat-meta', {}),
  exportUnmatched: () => post<{ ok: boolean; total: number; unique: number; path: string }>('/dev/export-unmatched', {}),
  getNodeTypeFilterOverrides: () => get<{ overrides: Record<string, FilterOverride> }>('/dev/node-type-filter/overrides'),
  addNodeTypeFilterOverride: (text: string, stat: string) => post<{ ok: boolean; key: string }>('/dev/node-type-filter/overrides', { text, stat }),
  deleteNodeTypeFilterOverride: (key: string) => del<{ ok: boolean }>(`/dev/node-type-filter/overrides/${encodeURIComponent(key)}`),
  getStatRecipes: (treeName: string, nodeType: string) =>
    get<StatRecipe[]>(`/dev/stat-recipes/${encodeURIComponent(treeName)}/${encodeURIComponent(nodeType)}`),
  getSnapshotModifiers: (treeName: string, nodeType: string) =>
    get<SnapshotModifier[]>(`/dev/snapshot-modifiers/${encodeURIComponent(treeName)}/${encodeURIComponent(nodeType)}`),

  clearSnapshot: () => del<{ ok: boolean }>('/dev/snapshot'),
  clearNodeTypeFilter: () => del<{ ok: boolean }>('/dev/node-type-filter'),

  // Seasons
  listSeasons: () => get<SeasonSummary[]>('/seasons'),
  getActiveSeason: () => get<{ name: string | null }>('/active-season'),
  setActiveSeason: (name: string | null) => post<{ ok: boolean }>('/active-season', { name }),
  deleteSeason: (name: string) => del<{ ok: boolean }>(`/seasons/${encodeURIComponent(name)}`),
  importSeason: (seasonName: string, nodes: object[]) =>
    post<{ ok: boolean; trees_imported: string[]; skipped: string[] }>(
      '/dev/import-season', { season_name: seasonName, nodes }
    ),
  importNewGodTalents: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; count: number }>(
      '/dev/import-new-god-talents', { season_name: seasonName, items }
    ),
  importLegendaryGear: (seasonName: string, fileData: object) =>
    post<{ ok: boolean; count: number; set_name: string }>(
      '/dev/import-legendary-gear', { season_name: seasonName, file_data: fileData }
    ),
  importCrawlerLegendaryGear: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; count: number }>(
      '/dev/import-crawler-legendary-gear',
      { season_name: seasonName, items }
    ),
  importSkills: (seasonName: string, fileData: object) =>
    post<{ ok: boolean; added: number; total: number }>(
      '/dev/import-skills', { season_name: seasonName, file_data: fileData }
    ),
  importCrawlerSkills: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; added: number; total: number }>(
      '/dev/import-crawler-skills', { season_name: seasonName, items }
    ),
  getSkills: () => get<{ season: string | null; skills: SkillItem[] }>('/skills'),
  getLegendaryGearIndex: () => get<{ season: string | null; items: LegendaryGearIndexItem[] }>('/legendary-gear-index'),
  getLegendaryGear: () => get<{ season: string | null; items: LegendaryGearItem[] }>('/legendary-gear'),
  clearSkills: () => del<{ ok: boolean }>('/dev/skills'),

  importCrawlerTree: (seasonName: string, treeName: string, crawlerData: object) =>
    post<ImportCrawlerTreeResult>(
      '/dev/import-crawler-tree',
      { season_name: seasonName, tree_name: treeName, crawler_data: crawlerData }
    ),

  importHeroTrait: (seasonName: string, fileData: object) =>
    post<{ ok: boolean; hero: string; total: number; heroes: number }>(
      '/dev/import-hero-traits', { season_name: seasonName, file_data: fileData }
    ),
  importCrawlerHeroTraits: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; added: number; total: number; heroes: number }>(
      '/dev/import-crawler-hero-traits', { season_name: seasonName, items }
    ),
  getHeroTraits: () => get<{ season: string | null; traits: HeroTrait[] }>('/hero-traits'),
  clearHeroTraits: () => del<{ ok: boolean }>('/dev/hero-traits'),

  importCrawlerPactSpirits: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; count: number }>(
      '/dev/import-crawler-pact-spirits', { season_name: seasonName, items }
    ),
  getPactSpirits: () => get<{ season: string | null; spirits: PactSpirit[] }>('/pact-spirits'),
  clearPactSpirits: () => del<{ ok: boolean }>('/dev/pact-spirits'),

  importCrawlerCraftBaseTypes: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; count: number }>(
      '/dev/import-crawler-craft-base-types', { season_name: seasonName, items }
    ),
  getCraftBaseTypes: () => get<{ season: string | null; base_types: CraftBaseType[] }>('/craft-base-types'),
  resolveGearAffixes: (texts: string[]) =>
    post<{ results: Record<string, ResolvedAffixFields> }>('/resolve-gear-affixes', { texts }),
  getCraftBaseItems: () => get<{ season: string | null; base_types: CraftBaseItemGroup[] }>('/craft-base-items'),
  clearCraftBaseTypes: () => del<{ ok: boolean }>('/dev/craft-base-types'),

  importCrawlerGrafts: (seasonName: string, items: object[]) =>
    post<{ ok: boolean; count: number }>(
      '/dev/import-crawler-grafts', { season_name: seasonName, items }
    ),
  getGrafts: () => get<{ season: string | null; grafts: Graft[] }>('/grafts'),
  clearGrafts: () => del<{ ok: boolean }>('/dev/grafts'),

  importDestiny: (seasonName: string, data: object) =>
    post<{ ok: boolean; count: number }>('/dev/import-destiny', { season_name: seasonName, data }),
  getDestiny: () => get<{ season: string | null; items: DestinyItem[] }>('/destiny'),

  importEtherealPrism: (seasonName: string, data: object) =>
    post<{ ok: boolean; count: number }>('/dev/import-ethereal-prism', { season_name: seasonName, data }),
  getEtherealPrism: () => get<{ season: string | null; modifiers: string[] }>('/ethereal-prism'),

  importHeroMemories: (seasonName: string, data: object) =>
    post<{ ok: boolean; count: number }>('/dev/import-hero-memories', { season_name: seasonName, data }),
  getHeroMemories: () => get<{
    season: string | null
    memory_types: HeroMemoryType[]
    fixed_affixes: HeroMemoryAffix[]
    random_affixes: HeroMemoryAffix[]
    base_stats: HeroMemoryAffix[]
  }>('/hero-memories'),

  importMemoryRevival: (seasonName: string, data: object) =>
    post<{ ok: boolean; count: number }>('/dev/import-memory-revival', { season_name: seasonName, data }),
  getMemoryRevival: () => get<{ season: string | null; affixes: MemoryRevivalAffix[] }>('/memory-revival'),

  importTowerSequence: (seasonName: string, data: object) =>
    post<{ ok: boolean; count: number }>('/dev/import-tower-sequence', { season_name: seasonName, data }),
  getTowerSequence: () => get<{ season: string | null; entries: TowerSequenceEntry[] }>('/tower-sequence'),

  diffSeasons: (seasonA: string, seasonB: string) =>
    post<SeasonDiff>('/dev/diff-seasons', { season_a: seasonA, season_b: seasonB }),

  getSlatePool: (primaryTree: string) =>
    get<SlatePool>(`/slate-pool/${encodeURIComponent(primaryTree)}`),
  getSlatePoolAll: () => get<SlatePool>('/slate-pool-all'),

  engineCompute: (payload: {
    slots: ({ treeName: string; nodeStates: Record<string, number> } | null)[]
    slates?: SavedSlate[]
    conditions?: string[]
    skill: {
      name: string; skill_type: string; tags: string[]; damage_types: string[]
      base_level: number; extra_levels?: number
      base_dmg_min?: number; base_dmg_max?: number; base_csr?: number
    }
    enemy?: {
      fire_resistance?: number; cold_resistance?: number
      lightning_resistance?: number; erosion_resistance?: number; armor?: number
    }
  }) => post<{
    avg_hit: number; min_hit: number; max_hit: number
    crit_chance: number; crit_multiplier: number; effective_dps: number
    breakdown: Record<string, unknown>
  }>('/engine/compute', payload),

  engineStats: (payload: {
    slots: ({ treeName: string; nodeStates: Record<string, number> } | null)[]
    slates?: SavedSlate[]
    condition_state?: Record<string, number | boolean>
    gear?: GearEngineItem[]
    character?: CharacterStatContribution[]
    memory_effects?: string[]
    spirit_effects?: string[]
  }) => post<StatSheetResponse>('/engine/stats', payload),

  getConditions: () => get<Record<string, ConditionDef[]>>('/conditions'),

  // ── Dev: condition manager ─────────────────────────────────────────────────
  devGetStatKeys: () =>
    get<{ keys: string[] }>('/dev/conditions/stat-keys'),
  devGetConditionDefs: () =>
    get<ConditionDefsResponse>('/dev/conditions/definitions'),
  devSaveConditionDef: (def: ConditionDef) =>
    post<{ ok: boolean }>('/dev/conditions/definitions', def),
  devUpdateConditionDef: (key: string, def: ConditionDef) =>
    put<{ ok: boolean }>(`/dev/conditions/definitions/${key}`, def),
  devDeleteConditionDef: (key: string) =>
    del<{ ok: boolean }>(`/dev/conditions/definitions/${key}`),
  devUpsertDerivedKey: (boolKey: string, stackKey: string) =>
    post<{ ok: boolean }>('/dev/conditions/derived-keys', { bool_key: boolKey, stack_key: stackKey }),
  devDeleteDerivedKey: (boolKey: string) =>
    del<{ ok: boolean }>(`/dev/conditions/derived-keys/${boolKey}`),
  devGetConditionSources: () =>
    get<{ season: string | null; entries: ConditionSourceEntry[] }>('/dev/conditions/sources'),
  devGetConditionSourceItems: (text: string) =>
    get<{ items: { source: string; item_name: string; affix_text: string }[] }>(`/dev/conditions/source-items?text=${encodeURIComponent(text)}`),
  devGetConditionOverrides: () =>
    get<Record<string, unknown>>('/dev/conditions/overrides'),
  devSaveConditionOverride: (conditionText: string, expression: unknown) =>
    post<{ ok: boolean }>('/dev/conditions/overrides', { condition_text: conditionText, expression }),
  devDeleteConditionOverride: (conditionText: string) =>
    del<{ ok: boolean }>('/dev/conditions/overrides', { condition_text: conditionText, expression: null }),

  validateAllocate: (
    tree_name: string,
    node_states: Record<string, number>,
    node_id: string,
    action: 'allocate' | 'deallocate'
  ) => post<{ allowed: boolean; node_states: Record<string, number> }>('/validate-allocate', {
    tree_name, node_states, node_id, action,
  }),
}
