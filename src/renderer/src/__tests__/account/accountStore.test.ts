import { describe, it, expect, vi } from 'vitest'
import { createAccountStore } from '../../store/accountStore'
import { AccountApiError, type Account } from '../../api/accounts'

const ACCOUNT: Account = {
  userId: 'usr_1',
  publicName: { name: 'Tyra', tag: '4472' },
  limits: { cloudBuilds: 20, profileBuilds: 10 },
  usage: { cloudBuilds: 0, profileBuilds: 0 },
}

function setup(over: Partial<Record<string, unknown>> = {}) {
  const api = {
    getAccount: vi.fn().mockResolvedValue(null),
    getSignupOffer: vi.fn().mockResolvedValue(null),
    completeSignup: vi.fn().mockResolvedValue(undefined),
    renameHandle: vi.fn().mockResolvedValue({ name: 'New', tag: '4472' }),
    signOut: vi.fn().mockResolvedValue(undefined),
    signOutEverywhere: vi.fn().mockResolvedValue(undefined),
    startReauth: vi.fn().mockResolvedValue('https://api.example.test/auth/discord/start?ticket=1'),
    exportAccount: vi.fn().mockResolvedValue({ builds: [] }),
    deleteAccount: vi.fn().mockResolvedValue(undefined),
    ...over,
  }
  const shell = {
    beginSignIn: vi.fn().mockResolvedValue({ ok: true }),
    endSession: vi.fn().mockResolvedValue(undefined),
    openReauth: vi.fn().mockResolvedValue({ ok: true }),
  }
  const records = { removeForAccount: vi.fn().mockResolvedValue(undefined) }
  const store = createAccountStore({ api: api as never, shell, records })
  return { store, api, shell, records }
}

describe('account store', () => {
  it('starts unknown and treats a guest as signed out', async () => {
    const { store } = setup()
    expect(store.getState().status).toBe('unknown')
    await store.getState().refresh()
    expect(store.getState().status).toBe('signed-out')
    expect(store.getState().account).toBeNull()
  })

  it('shows the signed-in account', async () => {
    const { store } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    await store.getState().refresh()
    expect(store.getState().status).toBe('signed-in')
    expect(store.getState().account?.publicName).toEqual({ name: 'Tyra', tag: '4472' })
  })

  it('offers sign-up when the session exists but no account has been created', async () => {
    const { store } = setup({ getSignupOffer: vi.fn().mockResolvedValue({ suggestedName: 'tyra_d', preview: { name: 'tyra_d', tag: '0918' } }) })
    await store.getState().refresh()
    expect(store.getState().status).toBe('signup')
    expect(store.getState().signupOffer?.suggestedName).toBe('tyra_d')
  })

  it('stays usable as a guest when the service is unreachable', async () => {
    const { store } = setup({ getAccount: vi.fn().mockRejectedValue(new AccountApiError(0, 'network_error', 'x')) })
    await store.getState().refresh()
    expect(store.getState().status).toBe('unavailable')
    expect(store.getState().account).toBeNull()
  })

  it('sign-in hands off to the shell and re-reads the account', async () => {
    const getAccount = vi.fn().mockResolvedValueOnce(null).mockResolvedValue(ACCOUNT)
    const { store, shell } = setup({ getAccount })
    await store.getState().refresh()
    await store.getState().signIn()
    expect(shell.beginSignIn).toHaveBeenCalledTimes(1)
    expect(store.getState().status).toBe('signed-in')
  })

  it('records a failed sign-in without changing state', async () => {
    const { store, shell } = setup()
    shell.beginSignIn.mockResolvedValue({ ok: false, error: 'cancelled' })
    await store.getState().signIn()
    expect(store.getState().error).toBe('cancelled')
    expect(store.getState().status).not.toBe('signed-in')
  })

  it('completes sign-up with the confirmed name', async () => {
    const getAccount = vi.fn().mockResolvedValueOnce(null).mockResolvedValue(ACCOUNT)
    const { store, api } = setup({ getAccount, getSignupOffer: vi.fn().mockResolvedValue({ suggestedName: 's', preview: null }) })
    await store.getState().refresh()
    await store.getState().completeSignup('Tyra')
    expect(api.completeSignup).toHaveBeenCalledWith('Tyra')
    expect(store.getState().status).toBe('signed-in')
  })

  it('sign-out clears the session locally even when the service call fails', async () => {
    const { store, api, shell } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    api.signOut.mockRejectedValue(new AccountApiError(0, 'network_error', 'x'))
    await store.getState().refresh()
    await store.getState().signOut()
    expect(shell.endSession).toHaveBeenCalled()
    expect(store.getState().status).toBe('signed-out')
    expect(store.getState().account).toBeNull()
  })

  it('sign out everywhere revokes remotely then ends the local session', async () => {
    const { store, api, shell } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    await store.getState().refresh()
    await store.getState().signOutEverywhere()
    expect(api.signOutEverywhere).toHaveBeenCalled()
    expect(shell.endSession).toHaveBeenCalled()
    expect(store.getState().status).toBe('signed-out')
  })

  it('rename updates the public name shown', async () => {
    const { store } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    await store.getState().refresh()
    await store.getState().rename('New')
    expect(store.getState().account?.publicName).toEqual({ name: 'New', tag: '4472' })
  })

  it('delete requires the service to accept it, then removes the account\'s local sync records', async () => {
    const { store, api, records } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    await store.getState().refresh()
    await store.getState().deleteAccount()
    expect(api.deleteAccount).toHaveBeenCalled()
    expect(records.removeForAccount).toHaveBeenCalledWith('usr_1')
    expect(store.getState().status).toBe('signed-out')
  })

  it('a refused delete (reauth required) keeps the account and its records', async () => {
    const { store, api, records } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    api.deleteAccount.mockRejectedValue(new AccountApiError(403, 'reauth_required', 'x'))
    await store.getState().refresh()
    await expect(store.getState().deleteAccount()).rejects.toMatchObject({ code: 'reauth_required' })
    expect(records.removeForAccount).not.toHaveBeenCalled()
    expect(store.getState().status).toBe('signed-in')
  })

  it('reauth starts a fresh Discord sign-in through the shell', async () => {
    const { store, shell } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    await store.getState().refresh()
    expect((await store.getState().reauth()).ok).toBe(true)
    expect(shell.openReauth).toHaveBeenCalledWith('https://api.example.test/auth/discord/start?ticket=1')
  })

  it('exports through the service and returns its data untouched', async () => {
    const { store } = setup({ getAccount: vi.fn().mockResolvedValue(ACCOUNT) })
    await store.getState().refresh()
    expect(await store.getState().exportData()).toEqual({ builds: [] })
  })
})
