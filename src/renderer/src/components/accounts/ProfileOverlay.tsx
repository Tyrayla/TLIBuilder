import React from 'react'
import AccountPanel from './AccountPanel'
import { useAccountStore } from '../../store/accountStore'
import { useEscapeToClose } from '../useEscapeToClose'
import OutsideDismissBackdrop from '../OutsideDismissBackdrop'

export default function ProfileOverlay({ onClose, onOpenCloudLibrary }: { onClose: () => void; onOpenCloudLibrary: () => void }) {
  const status = useAccountStore(s => s.status)
  const userId = useAccountStore(s => s.account?.userId)
  const title = status === 'signup' ? 'Create account' : status === 'signed-in' ? 'Profile settings' : 'Sign in'
  useEscapeToClose(onClose)
  return (
    <OutsideDismissBackdrop className="modal-backdrop" onDismiss={onClose}>
      <div className="modal-card settings-modal-card account-modal-card" role="dialog" aria-modal="true" aria-labelledby="profile-dialog-title" onClick={e => e.stopPropagation()}>
        <h3 className="modal-title" id="profile-dialog-title">{title}</h3>
        <div className="settings-modal-body">
          <AccountPanel key={`${status}:${userId ?? ''}`} onOpenCloudLibrary={onOpenCloudLibrary} />
        </div>
        <div className="modal-actions"><button className="btn btn-secondary" onClick={onClose}>Close</button></div>
      </div>
    </OutsideDismissBackdrop>
  )
}
