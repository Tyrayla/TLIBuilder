// Main-thread wrapper around the Pyodide compute worker (web build only). Spawns one worker, drives the
// init handshake, and exposes computeStats(reqJson) -> Promise<respJson>. The worker runs the real engine, so
// the returned JSON matches the desktop /api/engine/stats response shape exactly.

let worker: Worker | null = null
let readyPromise: Promise<void> | null = null
let nextId = 1
const pending = new Map<number, { resolve: (s: string) => void; reject: (e: Error) => void }>()
const progressListeners = new Set<(msg: string) => void>()

export function onComputeProgress(cb: (msg: string) => void): () => void {
  progressListeners.add(cb)
  return () => progressListeners.delete(cb)
}

interface WorkerOut {
  type: 'progress' | 'ready' | 'result' | 'error'
  msg?: string
  id?: number
  respJson?: string
}

/** Start the worker + load Pyodide/engine/data. Idempotent; returns a promise that resolves when ready. */
export function initPyodideCompute(dataBase: string, season: string): Promise<void> {
  if (readyPromise) return readyPromise
  worker = new Worker(new URL('./computeWorker.ts', import.meta.url), { type: 'module' })
  readyPromise = new Promise<void>((resolve, reject) => {
    worker!.onmessage = (e: MessageEvent<WorkerOut>) => {
      const m = e.data
      if (m.type === 'progress') { progressListeners.forEach(cb => cb(m.msg || '')); return }
      if (m.type === 'ready') {
        resolve()
        try { (window as unknown as Record<string, unknown>).__tliComputeReady = true; window.dispatchEvent(new Event('tli-compute-ready')) } catch { /* non-window ctx */ }
        return
      }
      if (m.type === 'result' && m.id != null) {
        pending.get(m.id)?.resolve(m.respJson || '{}'); pending.delete(m.id); return
      }
      if (m.type === 'error') {
        const err = new Error(m.msg || 'compute worker error')
        if (m.id != null) { pending.get(m.id)?.reject(err); pending.delete(m.id) }
        else { try { (window as unknown as Record<string, unknown>).__tliComputeError = m.msg } catch { /* */ } reject(err) }  // init error
      }
    }
    worker!.onerror = (e) => { try { (window as unknown as Record<string, unknown>).__tliComputeError = e.message } catch { /* */ } reject(new Error(`worker crashed: ${e.message}`)) }
  })
  const backendUrl = new URL('backend-py.zip', self.location.origin + import.meta.env.BASE_URL).href
  worker.postMessage({ type: 'init', backendUrl, dataBase, season })
  return readyPromise
}

/** Run one stat recompute in the worker. Resolves with the JSON response (same shape as the backend). */
export async function computeStats(reqJson: string): Promise<string> {
  if (!worker || !readyPromise) throw new Error('pyodide compute not initialized')
  await readyPromise
  const id = nextId++
  return new Promise<string>((resolve, reject) => {
    pending.set(id, { resolve, reject })
    worker!.postMessage({ type: 'compute', id, reqJson })
  })
}
