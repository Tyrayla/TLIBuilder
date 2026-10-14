import React, { useEffect, useRef, useState } from 'react'
import { friendlyAccountError } from '../../api/accounts'
import { getAccountStore, useAccountStore } from '../../store/accountStore'

export default function AccountMenu({ onOpenProfile, onOpenCloudLibrary }: { onOpenProfile: () => void; onOpenCloudLibrary: () => void }) {
  const status = useAccountStore(s => s.status)
  const account = useAccountStore(s => s.account)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    root.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus()
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  if (status !== 'signed-in' || !account) {
    return <button className="btn btn-secondary btn-sm build-select-account" onClick={onOpenProfile}>{status === 'signup' ? 'Finish signup' : 'Sign in'}</button>
  }
  const choose = (action: () => void) => { setOpen(false); action() }
  return (
    <div className="account-menu" ref={root} onKeyDown={e => {
      if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); trigger.current?.focus() }
      if (e.key === 'Tab' && open) setOpen(false)
      if (open && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
        e.preventDefault()
        const items = [...(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])]
        const i = items.indexOf(document.activeElement as HTMLButtonElement)
        const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
        items[next]?.focus()
      }
    }}>
      <button ref={trigger} className="btn btn-secondary btn-sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        {account.publicName.name}#{account.publicName.tag} <span aria-hidden="true">▾</span>
      </button>
      {open && <div className="account-menu-dropdown" role="menu" aria-label="Account">
        <button role="menuitem" onClick={() => choose(onOpenCloudLibrary)}>Cloud library</button>
        <button role="menuitem" onClick={() => choose(onOpenProfile)}>Profile settings</button>
        <button role="menuitem" disabled={busy} onClick={async () => {
          setBusy(true); setError(null)
          try { await getAccountStore().getState().signOut(); setOpen(false) }
          catch (e) { setError(friendlyAccountError(e)) }
          finally { setBusy(false) }
        }}>Sign out</button>
        {error && <p role="alert">{error}</p>}
      </div>}
    </div>
  )
}
