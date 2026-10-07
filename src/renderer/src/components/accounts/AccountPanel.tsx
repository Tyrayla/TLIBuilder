import React, { useEffect, useState } from 'react'
import { AccountApiError, accountTimestamp, friendlyAccountError, type Account, type SignupOffer } from '../../api/accounts'
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

function DiscordSignInButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button className="discord-sign-in" disabled={disabled} onClick={onClick}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M19.7 5.1a17 17 0 0 0-4.2-1.3l-.6 1.2a15.5 15.5 0 0 0-5.8 0l-.6-1.2a17 17 0 0 0-4.2 1.3C1.7 9 1 12.8 1.4 16.6a17 17 0 0 0 5.2 2.7l1.1-1.8-1.7-.8.4-.3c3.6 1.7 7.6 1.7 11.2 0l.4.3-1.7.8 1.1 1.8a17 17 0 0 0 5.2-2.7c.5-4.4-.8-8.1-3.2-11.5ZM8.8 14.2c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Zm6.4 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Z" />
      </svg>
      Continue with Discord
    </button>
  )
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
  const [retryAt, setRetryAt] = useState<number | undefined>()
  const [now, setNow] = useState(() => Date.now())
  const availableAt = retryAt ?? accountTimestamp(account?.nameChangeAvailableAt)
  const renameLocked = availableAt !== undefined && now < availableAt * 1000

  useEffect(() => {
    setRetryAt(undefined)
  }, [account?.userId, account?.nameChangeAvailableAt])
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const update = () => {
      setNow(Date.now())
      if (availableAt === undefined || availableAt * 1000 <= Date.now()) return
      // Thirty days exceeds the browser's largest timeout. Schedule the remaining time again.
      timer = setTimeout(update, Math.min(availableAt * 1000 - Date.now(), 2_147_483_647))
    }
    update()
    return () => clearTimeout(timer)
  }, [availableAt])

  const guard = async (fn: () => Promise<void>): Promise<void> => {
    setBusy(true)
    setLocalError(null)
    try { await fn() } catch (e) {
      if (e instanceof AccountApiError && e.code === 'name_change_cooldown') setRetryAt(accountTimestamp(e.details.retryAt))
      setLocalError(messageOf(e))
    } finally { setBusy(false) }
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

  if (status === 'unknown') return <section className="settings-section account-section"><h4 className="account-section-heading">Account</h4><div className="account-copy">Checking sign-in…</div></section>

  if (status === 'unavailable') {
    return (
      <section className="settings-section account-section">
        <h4 className="account-section-heading">Account</h4>
        <p className="account-copy">The account service is unavailable. Local builds still work.</p>
        <div className="settings-segmented" style={{ marginTop: 8 }}>
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.refresh)}>Try again</button>
        </div>
      </section>
    )
  }

  if (status === 'signed-out') {
    return (
      <section className="settings-section account-section">
        <h4 className="account-section-heading">Account</h4>
        <div className="settings-row">
          <div className="settings-row-label">
            <span>Discord sign-in is optional. Local builds and sharing work without an account.</span>
          </div>
          <DiscordSignInButton disabled={busy} onClick={() => void guard(actions.signIn)} />
        </div>
        {errorLine}
      </section>
    )
  }

  if (status === 'signup') {
    const value = nameTouched ? name : (signupOffer?.suggestedName ?? '')
    return (
      <section className="settings-section account-section">
        <h4 className="account-section-heading">Public name</h4>
        <p className="account-copy">Choose the name shown on your profile and shared builds.</p>
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
          <div className="account-copy">Your public name will be {signupOffer.preview.name}#{signupOffer.preview.tag}.</div>
        )}
        {errorLine}
      </section>
    )
  }

  // signed-in
  const publicName = account ? `${account.publicName.name}#${account.publicName.tag}` : ''
  const eligibilityMessage = availableAt === undefined
    ? null
    : renameLocked
      ? `Name change available ${new Date(availableAt * 1000).toLocaleDateString()}.`
      : 'Name change available now.'
  return (
    <div className="account-sections">
      <section className="settings-section account-section">
        <h4 className="account-section-heading">Public name</h4>
        <div className="account-public-name">{publicName}</div>
        {eligibilityMessage && <p className="account-eligibility">{eligibilityMessage}</p>}
      <details className="privacy-disclosure">
        <summary>Change public name</summary>
        <div className="settings-row">
        <input
          className="settings-select"
          disabled={busy || renameLocked}
          value={nameTouched ? name : (account?.publicName.name ?? '')}
          maxLength={24}
          aria-label="Change public name"
          onChange={(e) => { setName(e.target.value); setNameTouched(true) }}
        />
        <button
          className="settings-seg-btn"
          disabled={busy || !nameTouched || renameLocked}
          onClick={() => guard(async () => {
            if (availableAt !== undefined && Date.now() < availableAt * 1000) return
            if (!NAME_RULE.test(name)) throw new Error(NAME_RULE_TEXT)
            await actions.rename(name)
            setNameTouched(false)
          })}
        >Save name</button>
      </div>
      </details>
      </section>

      <section className="settings-section account-section">
        <h4 className="account-section-heading">Storage</h4>
        <div className="account-storage-row">
          <p className="account-copy">Cloud {account?.usage.cloudBuilds ?? 0} of {account?.limits.cloudBuilds ?? 20} · Profile {account?.usage.profileBuilds ?? 0} of {account?.limits.profileBuilds ?? 10}</p>
          <button className="settings-seg-btn" onClick={actions.openCloudLibrary}>Cloud library</button>
        </div>
      </section>

      <section className="settings-section account-section">
        <h4 className="account-section-heading">Sessions</h4>
      <div className="settings-row">
        <div className="settings-segmented">
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.signOut)}>Sign out</button>
          <button className="settings-seg-btn" disabled={busy} onClick={() => guard(actions.signOutEverywhere)}>Sign out everywhere</button>
        </div>
      </div>
      </section>

      <section className="settings-section account-section">
        <h4 className="account-section-heading">Your data</h4>
        <p className="account-copy">Export account data or permanently delete it.</p>
        <div className="settings-segmented">
          <button className="settings-seg-btn" disabled={busy} onClick={() => runGated('export')}>Export my data</button>
          <button className="settings-seg-btn" disabled={busy} onClick={() => { setDeleting(true); setConfirmText('') }}>Delete account</button>
        </div>
      </section>

      {deleting && (
        <div className="account-delete-confirmation">
          <p>Deletion removes your account, sessions, cloud builds, and named links. Backups expire within six months. Anonymous share links remain available, and public names stay reserved.</p>
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
          <p>Confirm with Discord to {gate.kind === 'export' ? 'export your data' : 'delete your account'}, then return here to continue.</p>
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
    </div>
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

/** Account controls in the dedicated profile dialog. */
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
  // Opening Profile rechecks once if the first check failed; nothing polls in the background.
  useEffect(() => {
    if (status === 'unavailable' || status === 'unknown') void getAccountStore().getState().refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return <AccountPanelView status={status} account={account} signupOffer={signupOffer} error={error} actions={actions} />
}
