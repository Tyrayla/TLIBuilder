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

export interface TreeSlot {
  treeName: string
  nodeStates: Record<string, number>
  coreTalentSelections?: Record<number, string>  // slot index → selected talent id
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
  conditions?: string[]
  conditionValues?: ConditionValues
  gear?: EquippedGearItem[]
  skills?: EquippedSkill[]
  characterLevel?: number
  hasPrism?: boolean
  traitId?: string | null
  traitLevel?: number          // legacy field — kept for loading old saves
  traitSlotLevels?: number[]   // [base, lv45, lv60, lv75], each 1–5
  advancedTraitSelections?: string[]
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
  reason?: 'ambiguous' | 'unmatched' | 'multi_text'
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

export interface ConditionMaximums {
  tenacity_max: number
  agility_max: number
  focus_max: number
  channeled_max_bonus: number  // add to skill's base channeled max to get the cap
}

export interface ConditionValues {
  tenacity_stacks: number
  agility_stacks: number
  focus_stacks: number
  channeled_stacks: number
  channeled_base_max: number  // inherited from skill; UI lets user set it
}

export interface StatSheetResponse {
  stats: Record<string, StatEntry>
  condition_maximums: ConditionMaximums
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
}

export interface SkillItem {
  item_id: string
  name: string
  description_lines: string[]
  raw_text: string
  skill_tags: string[]
}

export interface EquippedSupportSkill {
  support_index: number   // 1-5
  item_id: string
  name: string
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
function gearSlotEnergy(slot: GearSlot | null): number {
  if (!slot) return 0
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
  expression: string
  condition: string | null
  affix_kind: 'numeric' | 'special' | 'tagged' | 'placeholder'
  numeric_values: LegendaryNumericValue[]
  // resolved by backend at load time
  stat_key?: string | null
  unit?: string
}

export interface LegendaryGearItem {
  item_id: string
  name: string
  required_level: number
  affix_count: number
  affixes: LegendaryAffix[]
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
  slot: GearSlot | null
  base_stats?: Record<string, number>    // reserved for future base_type data
}

export interface GearAffixContribution {
  stat: string
  display_value: number
  unit: string
  item_name: string
  slot: string | null
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
  postBuild: (build: { id?: string; name: string; slots: (TreeSlot | null)[]; slates?: SavedSlate[]; conditions?: string[] }) =>
    post<Build>('/builds', build),
  deleteBuild: (id: string) => del<{ ok: boolean }>(`/builds/${id}`),

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
  importSkills: (seasonName: string, fileData: object) =>
    post<{ ok: boolean; added: number; total: number }>(
      '/dev/import-skills', { season_name: seasonName, file_data: fileData }
    ),
  getSkills: () => get<{ season: string | null; skills: SkillItem[] }>('/skills'),
  getLegendaryGear: () => get<{ season: string | null; items: LegendaryGearItem[] }>('/legendary-gear'),
  clearSkills: () => del<{ ok: boolean }>('/dev/skills'),

  importHeroTrait: (seasonName: string, fileData: object) =>
    post<{ ok: boolean; hero: string; total: number; heroes: number }>(
      '/dev/import-hero-traits', { season_name: seasonName, file_data: fileData }
    ),
  getHeroTraits: () => get<{ season: string | null; traits: HeroTrait[] }>('/hero-traits'),
  clearHeroTraits: () => del<{ ok: boolean }>('/dev/hero-traits'),
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
    conditions?: string[]
    gear?: GearEngineItem[]
    character?: CharacterStatContribution[]
  }) => post<StatSheetResponse>('/engine/stats', payload),

  getConditions: () => get<Record<string, ConditionDef[]>>('/conditions'),

  validateAllocate: (
    tree_name: string,
    node_states: Record<string, number>,
    node_id: string,
    action: 'allocate' | 'deallocate'
  ) => post<{ allowed: boolean; node_states: Record<string, number> }>('/validate-allocate', {
    tree_name, node_states, node_id, action,
  }),
}
