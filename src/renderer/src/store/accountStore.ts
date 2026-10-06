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
      try {
        const account = await deps.api.getAccount()
        if (account) { set({ status: 'signed-in', account, signupOffer: null, error: null }); return }
        const offer = await deps.api.getSignupOffer()
        if (offer) { set({ status: 'signup', account: null, signupOffer: offer, error: null }); return }
        set({ status: 'signed-out', account: null, signupOffer: null, error: null })
      } catch {
        // Offline or the service is down: carry on as a guest without an error banner.
        set({ status: 'unavailable', account: null, signupOffer: null })
      }
    },

    async signIn() {
      set({ error: null })
      const result = await deps.shell.beginSignIn()
      if (!result.ok) { set({ error: result.error ?? 'Sign-in did not complete.' }); return }
      await get().refresh()
    },

    async completeSignup(name) {
      await deps.api.completeSignup(name)
      await get().refresh()
    },

    async rename(name) {
      const publicName = await deps.api.renameHandle(name)
      const current = get().account
      if (current) set({ account: { ...current, publicName } })
    },

    async signOut() {
      try { await deps.api.signOut() } catch { /* the local session is dropped regardless */ }
      await deps.shell.endSession()
      set({ status: 'signed-out', account: null, signupOffer: null })
    },

    async signOutEverywhere() {
      await deps.api.signOutEverywhere()
      await deps.shell.endSession()
      set({ status: 'signed-out', account: null, signupOffer: null })
    },

    async reauth() {
      const url = await deps.api.startReauth()
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
      set({ status: 'signed-out', account: null, signupOffer: null })
    },
  }))
}

function defaultShell(): AccountShell {
  const bridge = typeof window !== 'undefined' ? window.api : undefined
  if (bridge?.accountSignIn) {
    return {
      beginSignIn: () => bridge.accountSignIn(),
      endSession: () => bridge.accountSignOut(),
      openReauth: (url) => bridge.accountReauth(url),
    }
  }
  return {
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
