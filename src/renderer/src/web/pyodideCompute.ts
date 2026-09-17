// Main-thread wrapper around the Pyodide backend worker (web build only). Spawns one worker, drives init, and
// exposes webApiRequest(method, path, body) -> Promise<data>, dispatching through the in-browser FastAPI app so
// responses match the desktop backend exactly.
import { errorFromResponse, normalizeError } from '../errors/tliError'

let worker: Worker | null = null
let readyPromise: Promise<void> | null = null
let nextId = 1
const pending = new Map<number, {
  resolve: (v: unknown) => void
  reject: (e: Error) => void
  timeout: ReturnType<typeof setTimeout>
}>()
const progressListeners = new Set<(msg: string) => void>()

// Pyodide has no threads: the worker runs one Python call at a time. Before this hardening, a request that
// never got a reply (a crashed worker, a malformed message, a genuinely stuck computation) left its Promise —
// and therefore the headline DPS loading state — pending forever, with no way to recover short of a page
// reload. Two mechanisms fix that: (1) every request/init carries a timeout that fails loudly instead of
// hanging, and (2) `webApiRequest` calls are serialized on the main thread so two callers (the headline
// recompute and a tooltip's damage-delta preview) never post concurrently into the same single-threaded worker.
const REQUEST_TIMEOUT_MS = 90_000
const INIT_TIMEOUT_MS = 180_000
let requestChain: Promise<void> = Promise.resolve()
let lastInit: { dataBase: string; season: string } | null = null

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

// A failed request's message, preferring the backend's own explanation (FastAPI's HTTPException body is
// {"detail": "..."}) over a bare status code — mirrors api/client.ts's errorMessage for the desktop path, kept
// separate so this module has no static dependency on client.ts (which dynamically imports this one).
function resultError(status: number, body?: string) {
  let parsed: unknown = null
  if (body) {
    try { parsed = JSON.parse(body) } catch { /* not JSON */ }
  }
  return errorFromResponse(parsed, 'TLI-UNEXPECTED-001', 'web.pyodide.request', `HTTP ${status}`, true)
}

// Reject every in-flight request and clear the queue — called when the worker can no longer be trusted to
// reply to anything it's already been sent (crash, timeout, unreadable message).
function rejectPending(error: Error): void {
  for (const entry of pending.values()) {
    clearTimeout(entry.timeout)
    entry.reject(error)
  }
  pending.clear()
}

// Tear down a worker that can no longer be trusted, and clear it (+ readyPromise) so the NEXT webApiRequest
// call spins up a fresh one (via lastInit) instead of joining a poisoned queue forever.
//
// Deliberately does NOT touch `requestChain`. Each webApiRequest call attaches to it synchronously, before
// its `run()` ever executes — so a request already queued behind the one that's crashing (call it p2) has
// already claimed its place in line by the time this runs. Resetting `requestChain` here would fork the
// queue: a brand-new call made shortly after the crash would attach to the fresh chain and could reach
// `postMessage` before p2's `run()` gets its turn on the old (still-draining) chain — two callers issuing
// concurrently into the same respawned worker, exactly the re-entrancy this serialization exists to prevent.
// Leaving `requestChain` alone keeps every caller — including one issued after the crash — behind whatever
// was already queued; the chain can't get stuck since every link resolves via `.then(fn, fn)` regardless of
// the previous outcome.
function failWorker(error: Error): void {
  rejectPending(error)
  if (worker) worker.terminate()
  worker = null
  readyPromise = null
  try { (window as unknown as Record<string, unknown>).__tliComputeError = error.message } catch { /* non-window ctx */ }
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
  lastInit = { dataBase, season }
  worker = new Worker(new URL('./computeWorker.ts', import.meta.url), { type: 'module' })
  readyPromise = new Promise<void>((resolve, reject) => {
    const initTimeout = setTimeout(() => {
      const err = normalizeError(new Error(`Engine startup timed out after ${INIT_TIMEOUT_MS / 1000}s`), 'TLI-BOOT-001', 'web.pyodide.init')
      failWorker(err)
      reject(err)
    }, INIT_TIMEOUT_MS)
    worker!.onmessage = (e: MessageEvent<WorkerOut>) => {
      const m = e.data
      if (m.type === 'progress') { progressListeners.forEach(cb => cb(m.msg || '')); return }
      if (m.type === 'ready') {
        clearTimeout(initTimeout)
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
        clearTimeout(p.timeout)
        if ((m.status ?? 500) >= 400) p.reject(resultError(m.status ?? 500, m.body))
        else { try { p.resolve(m.body ? JSON.parse(m.body) : null) } catch (e) { p.reject(e as Error) } }
        return
      }
      if (m.type === 'persist') { void idbPutSnapshot(m.snapshot || {}); return }
      if (m.type === 'error') {
        const err = normalizeError(new Error(m.msg || 'compute worker error'), 'TLI-BOOT-001', 'web.pyodide.worker')
        if (m.id != null) {
          const p = pending.get(m.id); pending.delete(m.id)
          if (p) { clearTimeout(p.timeout); p.reject(err) }
        } else {
          // An error with no request id means the worker failed outside any single request (e.g. during
          // init) — treat it like a crash: nothing already queued on this worker can be trusted either.
          clearTimeout(initTimeout)
          failWorker(err)
          reject(err)
        }
      }
    }
    worker!.onerror = (e) => {
      const err = normalizeError(new Error(`worker crashed: ${e.message}`), 'TLI-BOOT-001', 'web.pyodide.worker')
      clearTimeout(initTimeout)
      failWorker(err)
      reject(err)
    }
    // Fires when a posted message can't be structured-cloned/deserialized on the other side — rare, but same
    // "worker is no longer trustworthy" bucket as a crash.
    worker!.onmessageerror = () => {
      const err = normalizeError(new Error('worker sent an unreadable response'), 'TLI-BOOT-001', 'web.pyodide.worker')
      clearTimeout(initTimeout)
      failWorker(err)
      reject(err)
    }
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
 *  parsed response data (throws on non-2xx), matching the desktop get/post helpers. Serialized: only one
 *  request is ever in flight against the (single-threaded) Pyodide worker at a time. */
export async function webApiRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const run = async (): Promise<T> => {
    // A prior timeout/crash cleared worker+readyPromise. Recreate from the original web init parameters so
    // an ordinary build edit after a failure is a real retry, not a permanent "not initialized" error.
    if ((!worker || !readyPromise) && lastInit) initPyodideCompute(lastInit.dataBase, lastInit.season)
    if (!worker || !readyPromise) throw normalizeError(new Error('Pyodide backend is not initialized'), 'TLI-BOOT-001', 'web.pyodide.init')
    await readyPromise
    const id = nextId++
    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(() => {
        if (!pending.delete(id)) return   // already settled by a real response racing the timeout
        const err = normalizeError(new Error(`Engine request timed out after ${REQUEST_TIMEOUT_MS / 1000}s`), 'TLI-BOOT-001', 'web.pyodide.request')
        reject(err)
        failWorker(err)   // a request that never replied means the worker is stuck; don't trust it further
      }, REQUEST_TIMEOUT_MS)
      pending.set(id, { resolve: resolve as (v: unknown) => void, reject, timeout })
      worker!.postMessage({ type: 'request', id, method, path, bodyJson: body === undefined ? '' : JSON.stringify(body) })
    })
  }

  // Chain onto the previous request regardless of whether it resolved or rejected, so one failure doesn't
  // wedge every request queued after it.
  const queued = requestChain.then(run, run)
  requestChain = queued.then(() => undefined, () => undefined)
  return queued
}
