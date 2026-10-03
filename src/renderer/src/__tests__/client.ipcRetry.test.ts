import { describe, it, expect, vi, afterEach } from 'vitest'

// bug-288: on Electron, client.ts's IPC path (every request when window.api.apiRequest exists) makes a
// single attempt — unlike the HTTP path's 4-retry loop for network failures. Under a cold start or CPU
// load, a transport failure (status 0 / TLI-NET-001) is never retried, so a catalog fetch can fail
// permanently even though a moment later the backend would have answered fine. These tests drive the
// real `api.getSkills()` (client.ts's `get()`) against a mocked `window.api.apiRequest`, exercising the
// IPC branch exactly as Electron's preload bridge does.

async function freshApiModule() {
  vi.resetModules()
  return import('../api/client')
}

// Stubs a minimal window.api and runs the real initApi() so client.ts's module-level `ipcMode` flips
// on, same as the real Electron preload bridge does at boot.
async function setupIpc(initApi: typeof import('../api/client').initApi, apiRequest: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('window', {
    api: { apiRequest, getPythonPort: vi.fn().mockResolvedValue(8765), isVerbose: false },
  })
  await initApi()
}

const TRANSPORT_FAILURE = { ok: false, status: 0, data: { error: { code: 'TLI-NET-001', retryable: true } } }

describe('client.ts — IPC GET retries transport failures (bug-288)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('retries once on a retryable transport failure and resolves with the second response', async () => {
    const { api, initApi } = await freshApiModule()
    const skillsPayload = { season: 'S13', skills: [] }
    const apiRequest = vi.fn()
      .mockResolvedValueOnce(TRANSPORT_FAILURE)
      .mockResolvedValueOnce({ ok: true, status: 200, data: skillsPayload })
    await setupIpc(initApi, apiRequest)

    await expect(api.getSkills()).resolves.toEqual(skillsPayload)
    expect(apiRequest).toHaveBeenCalledTimes(2)
  })

  it('does not retry a non-transport failure (status 404) — called once, rejects', async () => {
    const { api, initApi } = await freshApiModule()
    const apiRequest = vi.fn().mockResolvedValue({ ok: false, status: 404, data: { error: { code: 'TLI-UNEXPECTED-001' } } })
    await setupIpc(initApi, apiRequest)

    await expect(api.getSkills()).rejects.toThrow()
    expect(apiRequest).toHaveBeenCalledTimes(1)
  })

  it('does not retry a non-transport failure (status 500) — called once, rejects', async () => {
    const { api, initApi } = await freshApiModule()
    const apiRequest = vi.fn().mockResolvedValue({ ok: false, status: 500, data: {} })
    await setupIpc(initApi, apiRequest)

    await expect(api.getSkills()).rejects.toThrow()
    expect(apiRequest).toHaveBeenCalledTimes(1)
  })

  it('stops after the same retry budget as the HTTP path: 4 retries = 5 calls, then rejects', async () => {
    vi.useFakeTimers()
    const { api, initApi } = await freshApiModule()
    const apiRequest = vi.fn().mockResolvedValue(TRANSPORT_FAILURE)
    await setupIpc(initApi, apiRequest)

    // Attach the rejection expectation immediately (before advancing timers) so a pending rejection
    // is never left unhandled while fake time is advanced.
    const assertion = expect(api.getSkills()).rejects.toThrow()
    await vi.advanceTimersByTimeAsync(400 + 800 + 1200 + 1600 + 100)
    await assertion
    expect(apiRequest).toHaveBeenCalledTimes(5)
  })

  it('backs off 400*(attempt+1) ms between retries, matching the HTTP path', async () => {
    vi.useFakeTimers()
    const { api, initApi } = await freshApiModule()
    const apiRequest = vi.fn()
      .mockResolvedValueOnce(TRANSPORT_FAILURE)
      .mockResolvedValueOnce({ ok: true, status: 200, data: { season: null, skills: [] } })
    await setupIpc(initApi, apiRequest)

    // Converted to an always-resolving outcome immediately, so advancing fake timers never leaves an
    // unhandled rejection sitting around while the retry (not yet implemented) hasn't happened.
    const outcome = api.getSkills().then(
      (v) => ({ settled: 'resolved' as const, v }),
      (e) => ({ settled: 'rejected' as const, e }),
    )
    await vi.advanceTimersByTimeAsync(0)
    expect(apiRequest).toHaveBeenCalledTimes(1)   // first attempt fired and failed
    await vi.advanceTimersByTimeAsync(399)
    expect(apiRequest).toHaveBeenCalledTimes(1)   // not yet — attempt 0's delay is 400*(0+1) = 400ms
    await vi.advanceTimersByTimeAsync(1)
    expect(apiRequest).toHaveBeenCalledTimes(2)   // retried right at 400ms
    await expect(outcome).resolves.toEqual({ settled: 'resolved', v: { season: null, skills: [] } })
  })
})
