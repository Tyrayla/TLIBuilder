// Main-thread wrapper around the Pyodide backend worker (web build only). Spawns one worker, drives init, and
// exposes webApiRequest(method, path, body) -> Promise<data>, dispatching through the in-browser FastAPI app so
// responses match the desktop backend exactly.

let worker: Worker | null = null
let readyPromise: Promise<void> | null = null
let nextId = 1
const pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>()
const progressListeners = new Set<(msg: string) => void>()

// Client-side build persistence (web only). The worker can't reliably write IndexedDB itself (Emscripten's
// in-worker IDBFS syncfs fails silently in Brave), so the main thread owns storage: it seeds the worker with the
// saved snapshot at init and re-writes it whenever the worker reports a mutation. One key holds a {path: text} map.
const IDB_NAME = 'tli-builds'
const IDB_STORE = 'kv'
const IDB_KEY = 'persist'

function openIdb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbGetSnapshot(): Promise<Record<string, string>> {
  try {
    const db = await openIdb()
    return await new Promise((resolve) => {
      const r = db.transaction(IDB_STORE, 'readonly').objectStore(IDB_STORE).get(IDB_KEY)
      r.onsuccess = () => resolve((r.result as Record<string, string>) || {})
      r.onerror = () => resolve({})
    })
  } catch { return {} }
}

async function idbPutSnapshot(snapshot: Record<string, string>): Promise<void> {
  try {
    const db = await openIdb()
    await new Promise<void>((resolve) => {
      const tx = db.transaction(IDB_STORE, 'readwrite')
      tx.objectStore(IDB_STORE).put(snapshot, IDB_KEY)
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
    })
  } catch { /* best-effort persist */ }
}

export function onComputeProgress(cb: (msg: string) => void): () => void {
  progressListeners.add(cb)
  return () => progressListeners.delete(cb)
}

interface WorkerOut {
  type: 'progress' | 'ready' | 'result' | 'error' | 'persist'
  msg?: string
  id?: number
  status?: number
  body?: string
  snapshot?: Record<string, string>
}

/** Start the worker + load Pyodide/engine/data. Idempotent; resolves when ready. */
export function initPyodideCompute(dataBase: string, season: string): Promise<void> {
  if (readyPromise) return readyPromise
  worker = new Worker(new URL('./computeWorker.ts', import.meta.url), { type: 'module' })
  readyPromise = new Promise<void>((resolve, reject) => {
    worker!.onmessage = (e: MessageEvent<WorkerOut>) => {
      const m = e.data
      if (m.type === 'progress') { progressListeners.forEach(cb => cb(m.msg || '')); return }
      if (m.type === 'ready') {
        resolve()
        try {
          const w = window as unknown as Record<string, unknown>
          w.__tliComputeReady = true
          w.__tliWebApi = webApiRequest   // diagnostic hook (smoke test / debugging)
          window.dispatchEvent(new Event('tli-compute-ready'))
        } catch { /* non-window ctx */ }
        return
      }
      if (m.type === 'result' && m.id != null) {
        const p = pending.get(m.id); pending.delete(m.id)
        if (!p) return
        if ((m.status ?? 500) >= 400) p.reject(new Error(`HTTP ${m.status}`))
        else { try { p.resolve(m.body ? JSON.parse(m.body) : null) } catch (e) { p.reject(e as Error) } }
        return
      }
      if (m.type === 'persist') { void idbPutSnapshot(m.snapshot || {}); return }
      if (m.type === 'error') {
        const err = new Error(m.msg || 'compute worker error')
        if (m.id != null) { pending.get(m.id)?.reject(err); pending.delete(m.id) }
        else { try { (window as unknown as Record<string, unknown>).__tliComputeError = m.msg } catch { /* */ } reject(err) }
      }
    }
    worker!.onerror = (e) => { try { (window as unknown as Record<string, unknown>).__tliComputeError = e.message } catch { /* */ } reject(new Error(`worker crashed: ${e.message}`)) }
  })
  // Read the saved builds from IndexedDB (main thread owns storage), then seed the worker with them at init.
  // ?v= is the zip's content hash (vite define) — busts browser/CDN caches exactly when the backend changes,
  // replacing the old cache:'reload' workaround that re-downloaded the zip on every visit.
  const zipVersion = typeof __BACKEND_ZIP_VERSION__ !== 'undefined' ? __BACKEND_ZIP_VERSION__ : 'dev'
  const backendUrl = new URL(`backend-py.zip?v=${zipVersion}`, self.location.origin + import.meta.env.BASE_URL).href
  void idbGetSnapshot().then(persistSnapshot => worker!.postMessage({ type: 'init', backendUrl, dataBase, season, persistSnapshot }))
  return readyPromise
}

/** Dispatch one request through the in-browser backend. `path` includes the /api prefix. Resolves with the
 *  parsed response data (throws on non-2xx), matching the desktop get/post helpers. */
export async function webApiRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (!worker || !readyPromise) throw new Error('pyodide backend not initialized')
  await readyPromise
  const id = nextId++
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve: resolve as (v: unknown) => void, reject })
    worker!.postMessage({ type: 'request', id, method, path, bodyJson: body === undefined ? '' : JSON.stringify(body) })
  })
}
