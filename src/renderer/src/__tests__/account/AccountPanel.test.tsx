import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { AccountPanelView, type AccountPanelActions } from '../../components/accounts/AccountPanel'
import PrivacySection from '../../components/accounts/PrivacySection'
import { useUiPrefs } from '../../store/uiPrefsStore'
import { AccountApiError, type Account } from '../../api/accounts'

vi.stubGlobal('window', new EventTarget())

const ACCOUNT: Account = {
  userId: 'usr_1', publicName: { name: 'Tyra', tag: '4472' },
  limits: { cloudBuilds: 20, profileBuilds: 10 }, usage: { cloudBuilds: 3, profileBuilds: 1 },
}

let renderer: TestRenderer.ReactTestRenderer | null = null
afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

const text = () => JSON.stringify(renderer!.toJSON())
const labels = () => renderer!.root.findAllByType('button').map((b) => b.children.join(''))
function click(label: string) {
  const b = renderer!.root.findAllByType('button').find((x) => x.children.join('') === label)
  if (!b) throw new Error(`no button "${label}"; have ${labels().join(' | ')}`)
  return act(async () => { await b.props.onClick() })
}

function actions(over: Partial<AccountPanelActions> = {}): AccountPanelActions {
  return {
    signIn: vi.fn().mockResolvedValue(undefined),
    completeSignup: vi.fn().mockResolvedValue(undefined),
    rename: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
    signOutEverywhere: vi.fn().mockResolvedValue(undefined),
    reauth: vi.fn().mockResolvedValue({ ok: true }),
    exportData: vi.fn().mockResolvedValue({ builds: [] }),
    deleteAccount: vi.fn().mockResolvedValue(undefined),
    openCloudLibrary: vi.fn(),
    saveExport: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
    ...over,
  }
}

function mount(props: Partial<React.ComponentProps<typeof AccountPanelView>> & { actions: AccountPanelActions }) {
  act(() => {
    renderer = TestRenderer.create(
      <AccountPanelView status="signed-in" account={ACCOUNT} signupOffer={null} error={null} {...props} />,
    )
  })
}

describe('AccountPanel — guest', () => {
  it('invites sign-in without making it a requirement', () => {
    mount({ status: 'signed-out', account: null, actions: actions() })
    expect(text()).toContain('optional')
    expect(labels()).toContain('Continue with Discord')
  })

  it('starts sign-in on click', async () => {
    const a = actions()
    mount({ status: 'signed-out', account: null, actions: a })
    await click('Continue with Discord')
    expect(a.signIn).toHaveBeenCalledTimes(1)
  })

  it('says plainly when the service is unreachable and keeps local use unaffected', () => {
    mount({ status: 'unavailable', account: null, actions: actions() })
    expect(text()).toContain('could not be reached')
    expect(text()).toContain('local')
  })

  it('lets the user try again instead of staying on the failure', async () => {
    const a = actions()
    mount({ status: 'unavailable', account: null, actions: a })
    await click('Try again')
    expect(a.refresh).toHaveBeenCalledTimes(1)
  })
})

describe('AccountPanel — sign-up', () => {
  const offer = { suggestedName: 'tyra_d', preview: { name: 'tyra_d', tag: '0918' } }

  it('shows the suggested public name, states it is public, and creates the account only on confirm', async () => {
    const a = actions()
    mount({ status: 'signup', account: null, signupOffer: offer, actions: a })
    expect(text()).toContain('tyra_d')
    expect(text().toLowerCase()).toContain('public')
    expect(a.completeSignup).not.toHaveBeenCalled()
    await click('Create account')
    expect(a.completeSignup).toHaveBeenCalledWith('tyra_d')
  })

  it('blocks a name that breaks the character rules before calling the service', async () => {
    const a = actions()
    mount({ status: 'signup', account: null, signupOffer: { suggestedName: 'bad name!', preview: null }, actions: a })
    await click('Create account')
    expect(a.completeSignup).not.toHaveBeenCalled()
    expect(text()).toContain('2–24')
  })
})

describe('AccountPanel — signed in', () => {
  it('shows the public name and usage against the limits', () => {
    mount({ actions: actions() })
    expect(text()).toContain('Tyra#4472')
    expect(text()).toContain('3 of 20')
  })

  it('sign out and sign out everywhere call their actions', async () => {
    const a = actions()
    mount({ actions: a })
    await click('Sign out')
    expect(a.signOut).toHaveBeenCalledTimes(1)
    await click('Sign out everywhere')
    expect(a.signOutEverywhere).toHaveBeenCalledTimes(1)
  })

  it('export downloads the data on success', async () => {
    const a = actions()
    mount({ actions: a })
    await click('Export my data')
    expect(a.saveExport).toHaveBeenCalledWith({ builds: [] })
  })

  it('export needing a fresh Discord sign-in asks for it, then retries on Continue', async () => {
    const exportData = vi.fn()
      .mockRejectedValueOnce(new AccountApiError(403, 'reauth_required', 'x'))
      .mockResolvedValue({ builds: [1] })
    const a = actions({ exportData })
    mount({ actions: a })
    await click('Export my data')
    expect(a.saveExport).not.toHaveBeenCalled()
    expect(text()).toContain('Confirm with Discord')
    await click('Confirm with Discord')
    expect(a.reauth).toHaveBeenCalledTimes(1)
    await click('Continue')
    expect(a.saveExport).toHaveBeenCalledWith({ builds: [1] })
  })

  it('delete is not sent until the user has read the consequences and typed DELETE', async () => {
    const a = actions()
    mount({ actions: a })
    await click('Delete account')
    expect(a.deleteAccount).not.toHaveBeenCalled()
    const t = text()
    expect(t).toContain('6 months')
    expect(t).toContain('Anonymous share links')
    const confirm = renderer!.root.findAllByType('button').find((b) => b.children.join('') === 'Permanently delete')!
    expect(confirm.props.disabled).toBe(true)
    const input = renderer!.root.findByProps({ 'aria-label': 'Type DELETE to confirm' })
    act(() => { input.props.onChange({ target: { value: 'DELETE' } }) })
    await click('Permanently delete')
    expect(a.deleteAccount).toHaveBeenCalledTimes(1)
  })

  it('delete needing a fresh Discord sign-in does not delete until reauth and Continue', async () => {
    const deleteAccount = vi.fn()
      .mockRejectedValueOnce(new AccountApiError(403, 'reauth_required', 'x'))
      .mockResolvedValue(undefined)
    const a = actions({ deleteAccount })
    mount({ actions: a })
    await click('Delete account')
    act(() => { renderer!.root.findByProps({ 'aria-label': 'Type DELETE to confirm' }).props.onChange({ target: { value: 'DELETE' } }) })
    await click('Permanently delete')
    expect(text()).toContain('Confirm with Discord')
    await click('Confirm with Discord')
    await click('Continue')
    expect(deleteAccount).toHaveBeenCalledTimes(2)
  })

  it('shows a service error without losing the panel', async () => {
    const a = actions({ signOutEverywhere: vi.fn().mockRejectedValue(new AccountApiError(0, 'network_error', 'The account service could not be reached.')) })
    mount({ actions: a })
    await click('Sign out everywhere')
    expect(text()).toContain('could not be reached')
    expect(labels()).toContain('Sign out')
  })

  it('opens the cloud library', async () => {
    const a = actions()
    mount({ actions: a })
    await click('Cloud library')
    expect(a.openCloudLibrary).toHaveBeenCalled()
  })
})

describe('PrivacySection', () => {
  it('explains the collection in plain language and lets the user turn it off', async () => {
    useUiPrefs.setState({ shareCompositionStats: true })
    act(() => { renderer = TestRenderer.create(<PrivacySection />) })
    const t = text()
    expect(t).toContain('catalog')
    expect(t).toContain('no account')
    expect(t.toLowerCase()).toContain('device')
    // Never call a persistent or hashed id anonymous: the stream has none.
    expect(t).not.toMatch(/hashed/i)
    await click('Off')
    expect(useUiPrefs.getState().shareCompositionStats).toBe(false)
    await click('On')
    expect(useUiPrefs.getState().shareCompositionStats).toBe(true)
  })

  it('states that guest use creates no account record', () => {
    act(() => { renderer = TestRenderer.create(<PrivacySection />) })
    expect(text()).toContain('Guest use')
  })
})
