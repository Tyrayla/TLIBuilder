import { describe, expect, it, vi } from 'vitest'
import { saveLocalThenMaybeUpload, shouldDismissSaveDialog } from '../utils/saveAndSync'

describe('saveLocalThenMaybeUpload', () => {
  it('saves locally before uploading when the user chose cloud storage', async () => {
    const events: string[] = []
    const result = await saveLocalThenMaybeUpload(
      async () => { events.push('local'); return { id: 'local-1', name: 'Build' } },
      'local-and-cloud',
      async id => { events.push(`cloud:${id}`); return { kind: 'uploaded', build: { cloudBuildId: 'cloud-1' } as never } },
    )

    expect(events).toEqual(['local', 'cloud:local-1'])
    expect(result).toEqual({ saved: { id: 'local-1', name: 'Build' }, upload: { kind: 'uploaded', build: { cloudBuildId: 'cloud-1' } } })
  })

  it('keeps the local save and returns the cloud error for the UI to explain', async () => {
    const saved = { id: 'local-1', name: 'Build' }
    const upload = vi.fn().mockRejectedValue(new Error('The account service is offline.'))
    const result = await saveLocalThenMaybeUpload(async () => saved, 'local-and-cloud', upload)

    expect(result.saved).toBe(saved)
    expect(result.upload).toEqual({ kind: 'error', code: 'unexpected', message: 'The account service is offline.' })
    expect(upload).toHaveBeenCalledWith('local-1')
  })

  it('retries the saved build upload without running the local Save As again', async () => {
    const events: string[] = []
    let localSaves = 0
    const saveLocal = async () => {
      localSaves += 1
      events.push('save:local-1')
      return { id: 'local-1', name: 'A Build' }
    }
    const upload = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ kind: 'uploaded', build: { cloudBuildId: 'cloud-1' } })
    const first = await saveLocalThenMaybeUpload(saveLocal, 'local-and-cloud', async (id) => {
      events.push(`upload:${id}`)
      return upload(id)
    })
    const retry = await saveLocalThenMaybeUpload(saveLocal, 'local-and-cloud', async (id) => {
      events.push(`upload:${id}`)
      return upload(id)
    }, first.saved)

    expect(events).toEqual(['save:local-1', 'upload:local-1', 'upload:local-1'])
    expect(localSaves).toBe(1)
    expect(retry).toEqual({ saved: { id: 'local-1', name: 'A Build' }, upload: { kind: 'uploaded', build: { cloudBuildId: 'cloud-1' } } })
  })

  it('does not upload when the local-only option is selected', async () => {
    const upload = vi.fn()
    const result = await saveLocalThenMaybeUpload(
      async () => ({ id: 'local-1', name: 'Build' }),
      'local-only',
      upload,
    )

    expect(result).toEqual({ saved: { id: 'local-1', name: 'Build' }, upload: null })
    expect(upload).not.toHaveBeenCalled()
  })
})

describe('save dialog dismissal', () => {
  it('closes immediately for local saves and successful or unchanged cloud saves', () => {
    expect(shouldDismissSaveDialog('local-only', null)).toBe(true)
    expect(shouldDismissSaveDialog('local-and-cloud', { kind: 'uploaded', build: {} as never })).toBe(true)
    expect(shouldDismissSaveDialog('local-and-cloud', { kind: 'unchanged' })).toBe(true)
  })

  it('keeps the dialog available to explain or retry a failed cloud upload', () => {
    expect(shouldDismissSaveDialog('local-and-cloud', { kind: 'error', code: 'offline', message: 'offline' })).toBe(false)
    expect(shouldDismissSaveDialog('local-and-cloud', { kind: 'quota-reached' })).toBe(false)
  })
})
