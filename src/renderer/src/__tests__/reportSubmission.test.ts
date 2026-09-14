import { afterEach, describe, expect, it, vi } from 'vitest'
import { submitBugReport } from '../api/share'

const payload = {
  category: 'other', runtime: 'desktop-electron', form_factor: 'desktop', transport: 'electron-ipc',
  app_version: 'test', description: 'Expected behavior:\na\n\nActual behavior:\nb', diagnostics: {},
}

afterEach(() => { Reflect.deleteProperty(globalThis, 'window') })

describe('report submission transport', () => {
  it('uses the fixed Electron main-process bridge when available', async () => {
    const reportRequest = vi.fn().mockResolvedValue({ ok: true, status: 201, data: { reportId: 'TLI-RPT-ABCDEFGH', status: 'received' } })
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { api: { reportRequest } as unknown as NonNullable<typeof window.api> },
    })
    await expect(submitBugReport(payload)).resolves.toEqual({ reportId: 'TLI-RPT-ABCDEFGH' })
    expect(reportRequest).toHaveBeenCalledWith(payload)
  })
})
