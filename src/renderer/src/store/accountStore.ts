// Account session state. Sign-in is optional: a guest (or an unreachable service) leaves every local
// feature working. The store never holds a session token; on desktop it lives in the main process, on
// web it is an HTTP-only cookie.
import { createStore, type StoreApi } from 'zustand/vanilla'
import { useStore } from 'zustand'
import {
  AccountApiError,
  getAccountsApi,
  webSignInUrl,
  type Account,
  type AccountsApi,
  type SignupOffer,
} from '../api/accounts'
import { defaultSyncRecordStore } from '../utils/syncRecords'
import { getShareBase } from '../api/share'

export type AccountStatus = 'unknown' | 'signed-out' | 'signup' | 'signed-in' | 'unavailable'

export interface AccountState {
  status: AccountStatus
  account: Account | null
  signupOffer: SignupOffer | null
  error: string | null
  /** Show a sign-in problem reported on return from the browser (web). */
  reportError: (message: string) => void
  refresh: () => Promise<void>
  signIn: () => Promise<void>
  completeSignup: (name: string) => Promise<void>
  rename: (name: string) => Promise<void>
  signOut: () => Promise<void>
  signOutEverywhere: () => Promise<void>
  reauth: () => Promise<{ ok: boolean; error?: string }>
  exportData: () => Promise<unknown>
  deleteAccount: () => Promise<void>
}

/** What differs between desktop and web. */
export interface AccountShell {
  /** Whether this device has ever signed in. A device that has not never asks the service anything. */
  hasSessionHint: () => boolean
  setSessionHint: (on: boolean) => void
  /** Desktop: the loopback flow, resolved when finished. Web: navigates away to Discord. */
  beginSignIn: () => Promise<{ ok: boolean; error?: string }>
  /** Forget the local session (desktop token, web nothing extra). */
  endSession: () => Promise<void>
  openReauth: (authorizeUrl: string) => Promise<{ ok: boolean; error?: string }>
}

export function createAccountStore(deps: {
  api: AccountsApi
  shell: AccountShell
  records: { removeForAccount: (userId: string) => Promise<void> }
  serviceBase?: string
}): StoreApi<AccountState> {
  return createStore<AccountState>((set, get) => ({
    status: 'unknown',
    account: null,
    signupOffer: null,
    error: null,

    reportError(message) {
      set({ error: message })
    },

    async refresh() {
      if (!deps.shell.hasSessionHint()) {
        set({ status: 'signed-out', account: null, signupOffer: null })
        return
      }
      try {
        const account = await deps.api.getAccount()
        if (account) { set({ status: 'signed-in', account, signupOffer: null, error: null }); return }
        const offer = await deps.api.getSignupOffer()
        if (offer) { set({ status: 'signup', account: null, signupOffer: offer, error: null }); return }
        // The web OAuth return may have ended without a session (for example, Discord consent was
        // cancelled). A stale hint would make every later load retry the same signed-out check.
        deps.shell.setSessionHint(false)
        set({ status: 'signed-out', account: null, signupOffer: null, error: null })
      } catch {
        // Offline or the service is down: carry on as a guest without an error banner.
        set({ status: 'unavailable', account: null, signupOffer: null })
      }
    },

    async signIn() {
      set({ error: null })
      // Remember before leaving: on web the sign-in navigates away and the next load must check the session.
      deps.shell.setSessionHint(true)
      const result = await deps.shell.beginSignIn()
      if (!result.ok) {
        deps.shell.setSessionHint(false)
        set({ error: result.error ?? 'Sign-in did not complete.' })
        return
      }
      await get().refresh()
    },

    async completeSignup(name) {
      await deps.api.completeSignup(name)
      await get().refresh()
    },

    async rename(name) {
      try {
        const { name: renamed, tag, nameChangeAvailableAt } = await deps.api.renameHandle(name)
        const current = get().account
        if (current) set({ account: { ...current, publicName: { name: renamed, tag }, nameChangeAvailableAt } })
      } catch (e) {
        const current = get().account
        if (current && e instanceof AccountApiError && e.code === 'name_change_cooldown' && typeof e.details.retryAt === 'number') {
          set({ account: { ...current, nameChangeAvailableAt: e.details.retryAt } })
        }
        throw e
      }
    },

    async signOut() {
      try { await deps.api.signOut() } catch { /* the local session is dropped regardless */ }
      await deps.shell.endSession()
      deps.shell.setSessionHint(false)
      set({ status: 'signed-out', account: null, signupOffer: null })
    },

    async signOutEverywhere() {
      await deps.api.signOutEverywhere()
      await deps.shell.endSession()
      deps.shell.setSessionHint(false)
      set({ status: 'signed-out', account: null, signupOffer: null })
    },

    async reauth() {
      let url: string
      try {
        url = await deps.api.startReauth()
        const target = new URL(url)
        const base = new URL(deps.serviceBase ?? getShareBase())
        if (target.origin !== base.origin || target.protocol !== base.protocol || target.username || target.password) {
          return { ok: false, error: 'The service returned an invalid reauthentication URL.' }
        }
      } catch {
        return { ok: false, error: 'The service returned an invalid reauthentication URL.' }
      }
      return deps.shell.openReauth(url)
    },

    exportData() {
      return deps.api.exportAccount()
    },

    async deleteAccount() {
      const userId = get().account?.userId
      await deps.api.deleteAccount()
      if (userId) await deps.records.removeForAccount(userId)
      await deps.shell.endSession()
      deps.shell.setSessionHint(false)
      set({ status: 'signed-out', account: null, signupOffer: null })
    },
  }))
}

function defaultShell(): AccountShell {
  const bridge = typeof window !== 'undefined' ? window.api : undefined
  if (bridge?.accountSignIn) {
    // The desktop bridge answers 401 locally when there is no token, so it never needs a hint.
    return {
      hasSessionHint: () => true,
      setSessionHint: () => undefined,
      beginSignIn: () => bridge.accountSignIn(),
      endSession: () => bridge.accountSignOut(),
      openReauth: (url) => bridge.accountReauth(url),
    }
  }
  // The web session cookie is HttpOnly, so a plain flag records that this browser has signed in.
  const HINT_KEY = 'tli-account-hint'
  return {
    hasSessionHint: () => {
      try { return window.localStorage.getItem(HINT_KEY) === '1' } catch { return false }
    },
    setSessionHint: (on) => {
      try { if (on) window.localStorage.setItem(HINT_KEY, '1'); else window.localStorage.removeItem(HINT_KEY) } catch { /* private mode */ }
    },
    beginSignIn: async () => {
      window.location.assign(webSignInUrl())
      return { ok: true }
    },
    endSession: async () => undefined,
    openReauth: async (url) => {
      window.location.assign(url)
      return { ok: true }
    },
  }
}

let singleton: StoreApi<AccountState> | null = null

export function getAccountStore(): StoreApi<AccountState> {
  if (!singleton) {
    singleton = createAccountStore({
      api: getAccountsApi(),
      shell: defaultShell(),
      records: defaultSyncRecordStore(),
    })
  }
  return singleton
}

export function useAccountStore<T>(selector: (state: AccountState) => T): T {
  return useStore(getAccountStore(), selector)
}

export { AccountApiError }
