import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Regression coverage for the class of bug behind the 1FrxGVV report: before this hardening, a request that
// never got a reply from the (single-threaded) Pyodide worker — a crash, an unreadable message, or a
// genuinely stuck computation — left its Promise, and therefore the headline DPS loading state, pending
// forever with no recovery short of a page reload. These tests drive a fake Worker directly so they exercise
// the real timeout/crash/retry logic in pyodideCompute.ts without needing a real browser or Pyodide.

// Flushes pending microtasks (requestChain.then chains, resolved-promise awaits) via a real macrotask —
// more reliable than counting `await Promise.resolve()` ticks against an implementation detail.
const flush = () => new Promise<void>(r => setTimeout(r, 0))

// ── Fake Worker ───────────────────────────────────────────────────────────────
class FakeWorker {
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: { message: string }) => void) | null = null
  onmessageerror: (() => void) | null = null
  posted: unknown[] = []
  terminated = false
  postMessage(msg: unknown) { this.posted.push(msg) }
  terminate() { this.terminated = true }
}
let workerInstances: FakeWorker[] = []

// ── Fake indexedDB (pyodideCompute persists builds via idbGetSnapshot/idbPutSnapshot at init) ──────────────
function installFakeIndexedDb() {
  const store: Record<string, unknown> = {}
  const fakeIndexedDb = {
    open: () => {
      const req: Record<string, unknown> = {}
      queueMicrotask(() => {
        req.result = {
          createObjectStore: () => {},
          transaction: () => ({
            objectStore: () => ({
              get: () => {
                const r: Record<string, unknown> = {}
                queueMicrotask(() => { r.result = store.persist; (r.onsuccess as (() => void) | undefined)?.() })
                return r
              },
              put: (value: unknown) => { store.persist = value },
            }),
          }),
        }
        ;(req.onsuccess as (() => void) | undefined)?.()
      })
      return req
    },
  }
  vi.stubGlobal('indexedDB', fakeIndexedDb)
}

function lastWorker(): FakeWorker {
  const w = workerInstances[workerInstances.length - 1]
  if (!w) throw new Error('no worker constructed yet')
  return w
}

function sendReady(w: FakeWorker) { w.onmessage?.({ data: { type: 'ready' } } as MessageEvent) }
function sendResult(w: FakeWorker, id: number, status: number, body: string) {
  w.onmessage?.({ data: { type: 'result', id, status, body } } as MessageEvent)
}
function requestMsgs(w: FakeWorker) {
  return w.posted.filter((m) => (m as { type: string }).type === 'request') as { id: number; bodyJson: string }[]
}

describe('pyodideCompute — worker hardening', () => {
  beforeEach(() => {
    vi.resetModules()
    workerInstances = []
    installFakeIndexedDb()
    vi.stubGlobal('self', { location: { origin: 'http://localhost' } })
    vi.stubGlobal('window', {})
    vi.stubGlobal('Worker', class extends FakeWorker {
      constructor() { super(); workerInstances.push(this) }
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('resolves a normal request with the parsed body', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const promise = webApiRequest('POST', '/api/engine/stats', { a: 1 })
    await flush()
    const sent = requestMsgs(lastWorker())[0]
    sendResult(lastWorker(), sent.id, 200, JSON.stringify({ ok: true }))
    await expect(promise).resolves.toEqual({ ok: true })
  })

  it('rejects with the backend detail message on a non-2xx response instead of a bare status', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const promise = webApiRequest('POST', '/api/engine/stats', {})
    await flush()
    const sent = requestMsgs(lastWorker())[0]
    sendResult(lastWorker(), sent.id, 422, JSON.stringify({ detail: 'Damage-taken reduction reached immunity (>=100%)...' }))
    await expect(promise).rejects.toThrow(/immunity/)
  })

  it('a request that never gets a reply times out, rejects, and terminates the worker', async () => {
    vi.useFakeTimers()
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const promise = webApiRequest('POST', '/api/engine/stats', {})
    const assertion = expect(promise).rejects.toThrow(/timed out/)
    await vi.advanceTimersByTimeAsync(90_000)
    await assertion
    expect(lastWorker().terminated).toBe(true)
  })

  it('a worker crash rejects the in-flight request, and a request queued behind it still gets a real retry', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const p1 = webApiRequest('POST', '/api/engine/stats', { a: 1 })
    await flush()
    // p2 is queued behind p1 (requests are serialized) — it hasn't reached any worker yet.
    const p2 = webApiRequest('POST', '/api/engine/stats', { a: 2 })
    lastWorker().onerror?.({ message: 'segfault' })
    await expect(p1).rejects.toThrow(/crashed/)

    // p2 doesn't inherit p1's crash silently — it gets its turn against a freshly spun-up worker.
    await flush()
    expect(workerInstances.length).toBe(2)
    sendReady(lastWorker())
    await flush()
    const sent = requestMsgs(lastWorker())[0]
    sendResult(lastWorker(), sent.id, 200, JSON.stringify({ ok: 2 }))
    await expect(p2).resolves.toEqual({ ok: 2 })
  })

  it('a call issued right after a crash does not jump ahead of one already queued behind the crashed one', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const p1 = webApiRequest('POST', '/api/engine/stats', { tag: 'p1' })
    await flush()
    const p2 = webApiRequest('POST', '/api/engine/stats', { tag: 'p2' })   // queued behind p1, not yet posted
    lastWorker().onerror?.({ message: 'segfault' })
    // Issued in the same tick as the crash, before p2 has had its turn — must still land BEHIND p2.
    const p3 = webApiRequest('POST', '/api/engine/stats', { tag: 'p3' })
    await expect(p1).rejects.toThrow(/crashed/)

    await flush()
    expect(workerInstances.length).toBe(2)   // p2's turn respawned the worker
    sendReady(lastWorker())
    await flush()

    // p2 must be the only thing posted so far — p3 is structurally unable to run until p2 SETTLES (it's
    // chained behind p2's own promise, not just behind the crash), so seeing it here would mean the fork
    // bug is back (a reset requestChain letting p3 attach to a fresh, independent chain).
    const tagOf = (m: { bodyJson: string }) => JSON.parse(m.bodyJson).tag
    expect(requestMsgs(lastWorker()).map(tagOf)).toEqual(['p2'])

    sendResult(lastWorker(), requestMsgs(lastWorker())[0].id, 200, '{}')
    await expect(p2).resolves.toEqual({})
    await flush()   // only now can p3's turn arrive

    expect(requestMsgs(lastWorker()).map(tagOf)).toEqual(['p2', 'p3'])
    sendResult(lastWorker(), requestMsgs(lastWorker())[1].id, 200, '{}')
    await expect(p3).resolves.toEqual({})
  })

  it('an unreadable worker message (onmessageerror) is treated like a crash', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const promise = webApiRequest('POST', '/api/engine/stats', {})
    await flush()
    lastWorker().onmessageerror?.()
    await expect(promise).rejects.toThrow(/unreadable/)
  })

  it('recovers on the next call after a crash — a fresh worker is created and the retry can succeed', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const failed = webApiRequest('POST', '/api/engine/stats', {})
    await flush()
    lastWorker().onerror?.({ message: 'boom' })
    await expect(failed).rejects.toThrow()

    expect(workerInstances.length).toBe(1)   // no new worker until the NEXT call
    const retried = webApiRequest('POST', '/api/engine/stats', {})
    await flush()
    expect(workerInstances.length).toBe(2)   // a fresh worker was spun up for the retry
    sendReady(lastWorker())
    await flush()
    const sent = requestMsgs(lastWorker())[0]
    sendResult(lastWorker(), sent.id, 200, JSON.stringify({ ok: true }))
    await expect(retried).resolves.toEqual({ ok: true })
  })

  it('serializes concurrent calls — the second request is not posted until the first resolves', async () => {
    const { initPyodideCompute, webApiRequest } = await import('../web/pyodideCompute')
    initPyodideCompute('https://data', 'SS13')
    sendReady(lastWorker())
    const p1 = webApiRequest('POST', '/api/engine/stats', { a: 1 })
    const p2 = webApiRequest('POST', '/api/engine/stats', { a: 2 })
    await flush()

    const w = lastWorker()
    expect(requestMsgs(w)).toHaveLength(1)   // p2 has not been posted into the (single-threaded) worker yet

    const first = requestMsgs(w)[0]
    sendResult(w, first.id, 200, JSON.stringify({ ok: 1 }))
    await expect(p1).resolves.toEqual({ ok: 1 })
    await flush()

    expect(requestMsgs(w)).toHaveLength(2)   // now p2 has gone out
    const second = requestMsgs(w)[1]
    sendResult(w, second.id, 200, JSON.stringify({ ok: 2 }))
    await expect(p2).resolves.toEqual({ ok: 2 })
  })
})
