let BASE = ''
export function getApiBase(): string { return BASE }

const rlog = (...args: unknown[]) => console.log('[api]', ...args)
const rerr = (...args: unknown[]) => console.error('[api]', ...args)

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

export interface Build {
  id?: string
  name: string
  slots: (TreeSlot | null)[]
}

export interface NodeStatData {
  stat: string
  display_name: string
  unit: string
  values: number[]
}

export interface TreeNode {
  id: string
  column: number
  row: number
  max_points: number
  node_type: string
  current_points: number
  stats: NodeStatData[]
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
}

export const api = {
  getTrees: () => get<{ name: string; color: string }[]>('/trees'),

  getTree: (name: string) => get<TreeData>(`/tree/${encodeURIComponent(name)}`),

  getBuilds: () => get<Build[]>('/builds'),
  postBuild: (build: { id?: string; name: string; slots: (TreeSlot | null)[] }) =>
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

  getNodeStats: () => get<Record<string, unknown>>('/node-stats'),
  getNodeStatsForNode: (treeName: string, nodeId: string) =>
    get<{ stat: string; values: number[] }[]>(
      `/node-stats/${encodeURIComponent(treeName)}/${encodeURIComponent(nodeId)}`
    ),
  postNodeStats: (treeName: string, nodeId: string, stats: { stat: string; values: number[] }[]) =>
    post(`/node-stats/${encodeURIComponent(treeName)}/${encodeURIComponent(nodeId)}`, { stats }),

  validateAllocate: (
    tree_name: string,
    node_states: Record<string, number>,
    node_id: string,
    action: 'allocate' | 'deallocate'
  ) => post<{ allowed: boolean; node_states: Record<string, number> }>('/validate-allocate', {
    tree_name, node_states, node_id, action,
  }),
}
