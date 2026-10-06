import React, { useEffect, useState } from 'react'
import { AccountApiError, friendlyAccountError, type Account, type SignupOffer } from '../../api/accounts'
import { getAccountStore, useAccountStore, type AccountStatus } from '../../store/accountStore'

export interface AccountPanelActions {
  signIn: () => Promise<void>
  completeSignup: (name: string) => Promise<void>
  rename: (name: string) => Promise<void>
  signOut: () => Promise<void>
  signOutEverywhere: () => Promise<void>
  reauth: () => Promise<{ ok: boolean; error?: string }>
  exportData: () => Promise<unknown>
  deleteAccount: () => Promise<void>
  openCloudLibrary: () => void
  saveExport: (data: unknown) => void
  refresh: () => Promise<void>
}

interface ViewProps {
  status: AccountStatus
  account: Account | null
  signupOffer: SignupOffer | null
  error: string | null
  actions: AccountPanelActions
}

const NAME_RULE = /^[A-Za-z0-9_.]{2,24}$/
const NAME_RULE_TEXT = 'Names use 2–24 letters, numbers, underscores, or dots.'

function messageOf(error: unknown): string {
  return friendlyAccountError(error)
}

type Gate = { kind: 'export' | 'delete'; started: boolean } | null

export function AccountPanelView({ status, account, signupOffer, error, actions }: ViewProps) {
  const [localError, setLocalError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [gate, setGate] = useState<Gate>(null)
  const [busy, setBusy] = useState(false)

  const guard = async (fn: () => Promise<void>): Promise<void> => {
    setBusy(true)
    setLocalError(null)
    try { await fn() } catch (e) { setLocalError(messageOf(e)) } finally { setBusy(false) }
  }

  // Export and delete need a Discord sign-in from the last 10 minutes. The service answers
  // reauth_required; the user confirms with Discord, then continues the same action.
  const runGated = (kind: 'export' | 'delete') => guard(async () => {
    try {
      if (kind === 'export') actions.saveExport(await actions.exportData())
      else await actions.deleteAccount()
      setGate(null)
    } catch (e) {
      if (e instanceof AccountApiError && e.code === 'reauth_required') { setGate({ kind, started: false }); return }
      throw e
    }
  })

  const shownError = localError ?? error
  const errorLine = shownError ? <p role="alert" style={{ color: 'var(--err)', fontSize: 13, margin: '8px 0 0' }}>{shownError}</p> : null

  if (status === 'unknown') return <section className="settings-section"><h4 className="settings-section-title">Account</h4><div className="settings-row-hint">Checking sign-in…</div></section>

  if (status === 'unavailable') {
    return (
      <section className="settings-section">
        <h4 className="settings-section-title">Account</h4>
        <div className="settings-row-hint">
          The account service could not be reached. Everything on this device still works, and local builds are not affected.
        </div>
        <div className="settings-segmented" style={{ marginTop: 8 }}>
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.refresh)}>Try again</button>
        </div>
      </section>
    )
  }

  if (status === 'signed-out') {
    return (
      <section className="settings-section">
        <h4 className="settings-section-title">Account</h4>
        <div className="settings-row">
          <div className="settings-row-label">
            <span>Cloud builds and a public name</span>
            <span className="settings-row-hint">
              Signing in is optional. Calculating, importing, exporting, and sharing links work without an account.
              Signing in with Discord only reads your Discord user ID and username; it does not request your email or servers.
            </span>
          </div>
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.signIn)}>Continue with Discord</button>
        </div>
        {errorLine}
      </section>
    )
  }

  if (status === 'signup') {
    const value = nameTouched ? name : (signupOffer?.suggestedName ?? '')
    return (
      <section className="settings-section">
        <h4 className="settings-section-title">Choose your public name</h4>
        <div className="settings-row-hint" style={{ marginBottom: 8 }}>
          Your public name is visible to anyone who opens one of your shared builds or your profile. It does not need to
          match your Discord username. The service adds a four-digit tag, for example Tyra#4472.
        </div>
        <div className="settings-row">
          <input
            className="settings-select"
            value={value}
            maxLength={24}
            aria-label="Public name"
            onChange={(e) => { setName(e.target.value); setNameTouched(true) }}
          />
          <button
            className="settings-seg-btn"
            disabled={busy}
            onClick={() => guard(async () => {
              if (!NAME_RULE.test(value)) throw new Error(NAME_RULE_TEXT)
              await actions.completeSignup(value)
            })}
          >Create account</button>
        </div>
        {signupOffer?.preview && !nameTouched && (
          <div className="settings-row-hint">You would appear as {signupOffer.preview.name}#{signupOffer.preview.tag}.</div>
        )}
        {errorLine}
      </section>
    )
  }

  // signed-in
  const publicName = account ? `${account.publicName.name}#${account.publicName.tag}` : ''
  return (
    <section className="settings-section">
      <h4 className="settings-section-title">Account</h4>
      <div className="settings-row">
        <div className="settings-row-label">
          <span>{publicName}</span>
          <span className="settings-row-hint">
            {account ? `${account.usage.cloudBuilds} of ${account.limits.cloudBuilds} cloud builds, ${account.usage.profileBuilds} of ${account.limits.profileBuilds} on your profile` : ''}
          </span>
        </div>
        <button className="settings-seg-btn" onClick={actions.openCloudLibrary}>Cloud library</button>
      </div>
      <div className="settings-row">
        <input
          className="settings-select"
          value={nameTouched ? name : (account?.publicName.name ?? '')}
          maxLength={24}
          aria-label="Change public name"
          onChange={(e) => { setName(e.target.value); setNameTouched(true) }}
        />
        <button
          className="settings-seg-btn"
          disabled={busy || !nameTouched}
          onClick={() => guard(async () => {
            if (!NAME_RULE.test(name)) throw new Error(NAME_RULE_TEXT)
            await actions.rename(name)
            setNameTouched(false)
          })}
        >Save name</button>
      </div>
      <div className="settings-row">
        <div className="settings-segmented">
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.signOut)}>Sign out</button>
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.signOutEverywhere)}>Sign out everywhere</button>
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span>Your data</span>
          <span className="settings-row-hint">Export or delete your account. Both ask you to confirm with Discord again first.</span>
        </div>
        <div className="settings-segmented">
          <button className="settings-seg-btn" disabled={busy} onClick={() => runGated('export')}>Export my data</button>
          <button className="settings-seg-btn" disabled={busy} onClick={() => { setDeleting(true); setConfirmText('') }}>Delete account</button>
        </div>
      </div>

      {deleting && (
        <div className="settings-row-hint" style={{ border: '1px solid var(--err)', borderRadius: 6, padding: 10, marginTop: 8 }}>
          <p style={{ margin: '0 0 8px' }}>
            Deleting your account removes it, your sessions, your cloud builds, and your named links from the live service.
            Backups keep deleted data until they expire, at most 6 months. Anonymous share links have no owner and stay
            available. Your handle and link names stay reserved so they never point at someone else.
          </p>
          <input
            className="settings-select"
            aria-label="Type DELETE to confirm"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
          />
          <div className="settings-segmented" style={{ marginTop: 8 }}>
            <button className="settings-seg-btn" disabled={busy || confirmText !== 'DELETE'} onClick={() => runGated('delete')}>Permanently delete</button>
            <button className="settings-seg-btn" disabled={busy} onClick={() => { setDeleting(false); setGate(null) }}>Cancel</button>
          </div>
        </div>
      )}

      {gate && (
        <div className="settings-row-hint" style={{ marginTop: 8 }}>
          <p style={{ margin: '0 0 8px' }}>
            To {gate.kind === 'export' ? 'export your data' : 'delete your account'}, confirm with Discord again. Finish in your
            browser, then come back and continue.
          </p>
          <div className="settings-segmented">
            {!gate.started ? (
              <button
                className="settings-seg-btn"
                disabled={busy}
                onClick={() => guard(async () => {
                  const result = await actions.reauth()
                  if (!result.ok) throw new Error(result.error ?? 'Could not start the Discord sign-in.')
                  setGate({ ...gate, started: true })
                })}
              >Confirm with Discord</button>
            ) : (
              <button className="settings-seg-btn" disabled={busy} onClick={() => runGated(gate.kind)}>Continue</button>
            )}
          </div>
        </div>
      )}
      {errorLine}
    </section>
  )
}

function downloadJson(data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'tli-builder-account-export.json'
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Connected panel for the Settings overlay. */
export default function AccountPanel({ onOpenCloudLibrary }: { onOpenCloudLibrary: () => void }) {
  const status = useAccountStore((s) => s.status)
  const account = useAccountStore((s) => s.account)
  const signupOffer = useAccountStore((s) => s.signupOffer)
  const error = useAccountStore((s) => s.error)
  const actions: AccountPanelActions = {
    signIn: () => getAccountStore().getState().signIn(),
    completeSignup: (n) => getAccountStore().getState().completeSignup(n),
    rename: (n) => getAccountStore().getState().rename(n),
    signOut: () => getAccountStore().getState().signOut(),
    signOutEverywhere: () => getAccountStore().getState().signOutEverywhere(),
    reauth: () => getAccountStore().getState().reauth(),
    exportData: () => getAccountStore().getState().exportData(),
    deleteAccount: () => getAccountStore().getState().deleteAccount(),
    openCloudLibrary: onOpenCloudLibrary,
    saveExport: downloadJson,
    refresh: () => getAccountStore().getState().refresh(),
  }
  // Opening Settings rechecks once if the first check failed; nothing polls in the background.
  useEffect(() => {
    if (status === 'unavailable' || status === 'unknown') void getAccountStore().getState().refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return <AccountPanelView status={status} account={account} signupOffer={signupOffer} error={error} actions={actions} />
}
