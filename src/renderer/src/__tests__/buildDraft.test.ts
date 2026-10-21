import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

function installDraftStorage() {
  const records = new Map<string, unknown>()
  const session = new Map<string, string>()
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => session.get(key) ?? null,
    setItem: (key: string, value: string) => session.set(key, value),
  })
  vi.stubGlobal('indexedDB', {
    open: () => {
      const request: Record<string, unknown> = {}
      const stores = new Set<string>()
      queueMicrotask(() => {
        request.result = {
          objectStoreNames: { contains: (name: string) => stores.has(name) },
          createObjectStore: (name: string) => stores.add(name),
          transaction: () => {
            const transaction: Record<string, unknown> = {
              objectStore: () => ({
                get: (key: string) => {
                  const getRequest: Record<string, unknown> = {}
                  queueMicrotask(() => {
                    getRequest.result = records.get(key)
                    ;(getRequest.onsuccess as (() => void) | undefined)?.()
                  })
                  return getRequest
                },
                put: (value: unknown, key: string) => records.set(key, value),
                delete: (key: string) => records.delete(key),
              }),
            }
            queueMicrotask(() => (transaction.oncomplete as (() => void) | undefined)?.())
            return transaction
          },
        }
        ;(request.onupgradeneeded as (() => void) | undefined)?.()
        ;(request.onsuccess as (() => void) | undefined)?.()
      })
      return request
    },
  })
  return session
}

describe('web build draft storage', () => {
  let session: Map<string, string>

  beforeEach(() => {
    vi.resetModules()
    session = installDraftStorage()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('round trips the active build and clears it after discard', async () => {
    const { clearBuildDraft, readBuildDraft, writeBuildDraft } = await import('../utils/buildDraft')
    const draft = {
      version: 1 as const,
      savedAt: 1234,
      buildId: 'build-7',
      buildName: 'Frost build',
      activeSlot: 2,
      payload: { characterLevel: 91, notes: 'keep this edit' },
      dirty: true,
      screen: 'gear',
    }

    await writeBuildDraft(draft)
    expect(await readBuildDraft()).toEqual(draft)

    await clearBuildDraft()
    expect(await readBuildDraft()).toBeNull()
  })

  it('keeps drafts isolated between browser tabs', async () => {
    const { readBuildDraft, writeBuildDraft } = await import('../utils/buildDraft')
    const draft = {
      version: 1 as const,
      savedAt: 1234,
      buildId: null,
      buildName: 'Untitled',
      activeSlot: 0,
      payload: { characterLevel: 100 },
      dirty: true,
      screen: 'hero-traits',
    }

    session.set('tlibuilder-web-draft-tab', 'tab-one')
    await writeBuildDraft(draft)
    session.set('tlibuilder-web-draft-tab', 'tab-two')
    expect(await readBuildDraft()).toBeNull()
    session.set('tlibuilder-web-draft-tab', 'tab-one')
    expect(await readBuildDraft()).toEqual(draft)
  })
})
