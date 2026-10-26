const DB_NAME = 'tlibuilder-web-session'
const DB_VERSION = 1
const STORE_NAME = 'drafts'
const TAB_ID_KEY = 'tlibuilder-web-draft-tab'

function activeDraftKey(): string {
  let tabId = sessionStorage.getItem(TAB_ID_KEY)
  if (!tabId) {
    tabId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(TAB_ID_KEY, tabId)
  }
  return `active:${tabId}`
}

export interface BuildDraft {
  version: 1
  savedAt: number
  buildId: string | null
  buildName: string
  activeSlot: number
  payload: Record<string, unknown>
  dirty: boolean
  screen: string
}

let databasePromise: Promise<IDBDatabase> | null = null

function openDatabase(): Promise<IDBDatabase> {
  if (databasePromise) return databasePromise
  const opening = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME)
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Could not open the web draft database'))
    request.onblocked = () => reject(new Error('The web draft database is blocked by another tab'))
  }).catch(error => {
    databasePromise = null
    throw error
  })
  databasePromise = opening
  return opening
}

export async function readBuildDraft(): Promise<BuildDraft | null> {
  const db = await openDatabase()
  const key = activeDraftKey()
  return new Promise((resolve, reject) => {
    const request = db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).get(key)
    request.onsuccess = () => {
      const value = request.result as BuildDraft | undefined
      const valid = !!value
        && value.version === 1
        && value.payload !== null
        && typeof value.payload === 'object'
        && !Array.isArray(value.payload)
        && (value.buildId === null || typeof value.buildId === 'string')
        && typeof value.buildName === 'string'
        && Number.isInteger(value.activeSlot)
        && typeof value.dirty === 'boolean'
        && typeof value.screen === 'string'
      resolve(valid && value ? value : null)
    }
    request.onerror = () => reject(request.error ?? new Error('Could not read the web draft'))
  })
}

export async function writeBuildDraft(draft: BuildDraft): Promise<void> {
  const db = await openDatabase()
  const key = activeDraftKey()
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).put(draft, key)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error ?? new Error('Could not save the web draft'))
    transaction.onabort = () => reject(transaction.error ?? new Error('Saving the web draft was aborted'))
  })
}

export async function clearBuildDraft(): Promise<void> {
  const db = await openDatabase()
  const key = activeDraftKey()
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).delete(key)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error ?? new Error('Could not clear the web draft'))
    transaction.onabort = () => reject(transaction.error ?? new Error('Clearing the web draft was aborted'))
  })
}
