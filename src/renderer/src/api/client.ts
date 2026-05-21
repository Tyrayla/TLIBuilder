let BASE = ''
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
  if (window.api) {
    rlog('initApi — Electron path: calling getPythonPort via IPC')
    const port = await window.api.getPythonPort()
    BASE = `http://127.0.0.1:${port}/api`
    rlog(`initApi — IPC returned port ${port}, BASE set to: ${BASE}`)
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
  const url = `${BASE}${path}`
  rlog(`POST ${url}`)
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  rlog(`POST ${url} — status ${res.status}`)
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json()
}

async function del<T>(path: string, body?: unknown): Promise<T> {
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

export interface TreeData {
  name: string
  nodes: TreeNode[]
  connections: { from: string; to: string }[]
  core_talent_slots: { id: string; label: string }[]
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

export interface StatSheetResponse {
  stats: Record<string, StatEntry>
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
  is_active: boolean
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
