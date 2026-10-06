import React, { useCallback, useState } from 'react'
import type { HeroTrait } from '../../api/client'
import type { CloudSync, ConflictOutcome, DownloadOutcome, ResolveOutcome, UploadOutcome } from '../../utils/cloudSync'
import { summarizeCode } from '../../utils/buildSummary'
import ConflictDialog, { type ConflictSide } from './ConflictDialog'
import { LinkPromptDialog, LinkUpdateDialog, NoticeDialog, ShortenNameDialog } from './CloudDialogs'

type Dialog =
  | { kind: 'notice'; title: string; body: string; actions?: { label: string; onClick: () => void }[] }
  | { kind: 'shorten'; localId: string; currentName: string; suggested: string }
  | { kind: 'link-prompt'; localId: string; cloudBuildId: string; cloudBuildName: string }
  | { kind: 'conflict'; localId: string; conflict: ConflictOutcome; local: ConflictSide; cloud: ConflictSide; error: string | null }
  | { kind: 'link-update'; cloudBuildId: string; revisionId: string }

interface Options {
  sync: CloudSync
  /** Called after anything that changed local builds, cloud builds, or sync records. */
  onChanged: () => void
  requestSignIn: () => void
  /** The named-link path of the cloud build behind a local build, when it has one. */
  linkPathFor: (localId: string) => string | null
  heroTraits: HeroTrait[] | null
  /** Unix seconds a local build was last saved, for the conflict screen. */
  localSavedAtFor?: (localId: string) => number | null
}

export function useCloudActions(opts: Options) {
  const { sync, onChanged, requestSignIn, linkPathFor, heroTraits, localSavedAtFor } = opts
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [busy, setBusy] = useState(false)

  const close = useCallback(() => setDialog(null), [])
  const notice = useCallback((title: string, body: string, actions?: { label: string; onClick: () => void }[]) => {
    setDialog({ kind: 'notice', title, body, actions })
  }, [])

  const openConflict = useCallback(async (localId: string, conflict: ConflictOutcome, error: string | null) => {
    const [localSummary, cloudSummary] = await Promise.all([
      summarizeCode(conflict.local.code, heroTraits),
      summarizeCode(conflict.cloud.code, heroTraits),
    ])
    setDialog({
      kind: 'conflict', localId, conflict, error,
      local: { name: conflict.local.name, savedAt: localSavedAtFor?.(localId) ?? null, ...localSummary },
      cloud: { name: conflict.cloud.build.name, savedAt: conflict.cloud.build.updatedAt, ...cloudSummary },
    })
  }, [heroTraits, localSavedAtFor])

  const showUpload = useCallback(async (localId: string, outcome: UploadOutcome | ResolveOutcome): Promise<void> => {
    switch (outcome.kind) {
      case 'sign-in-required': setDialog(null); requestSignIn(); return
      case 'uploaded': notice('Uploaded', 'This build is saved to your cloud library.'); onChanged(); return
      case 'unchanged': notice('Already up to date', 'The cloud copy matches this build.'); return
      case 'shorten-name': {
        setDialog({ kind: 'shorten', localId, currentName: outcome.currentName, suggested: outcome.suggestedName }); return
      }
      case 'link-prompt':
        setDialog({ kind: 'link-prompt', localId, cloudBuildId: outcome.cloudBuildId, cloudBuildName: outcome.cloudBuildName }); return
      case 'cloud-newer':
        notice('A newer version is in the cloud', 'Use Download from cloud to get it. Nothing was uploaded.'); return
      case 'cloud-missing':
        notice('The cloud copy was deleted', 'This build was linked to a cloud build that no longer exists. You can upload it as a new cloud build.', [
          { label: 'Upload as a new build', onClick: () => { void sync.unlink(localId).then(() => startUploadRef.current?.(localId)) } },
        ]); return
      case 'quota-reached':
        notice('Cloud library is full', 'Your account can keep up to 20 cloud builds. Delete one from the cloud library to make room.'); return
      case 'conflict': await openConflict(localId, outcome, null); return
      case 'kept-both':
        notice('Saved as a new local build', 'The cloud version is now a separate local build. Your build was left as it is.'); onChanged(); return
      case 'replaced-local':
        notice('Local build replaced', 'This build now matches the cloud version.'); onChanged(); return
      case 'needs-confirmation': return
      case 'error': notice('Something went wrong', outcome.message); return
    }
  }, [notice, onChanged, openConflict, requestSignIn, sync])

  const startUploadRef = React.useRef<((localId: string) => Promise<void>) | null>(null)

  const startUpload = useCallback(async (localId: string) => {
    await showUpload(localId, await sync.upload(localId, {}))
  }, [showUpload, sync])
  startUploadRef.current = startUpload

  const startDownload = useCallback(async (localId: string) => {
    const outcome: DownloadOutcome = await sync.download(localId)
    switch (outcome.kind) {
      case 'sign-in-required': requestSignIn(); return
      case 'downloaded': notice('Downloaded', 'This build now matches the cloud version.'); onChanged(); return
      case 'downloaded-new': notice('Downloaded', 'The cloud build was saved as a local build.'); onChanged(); return
      case 'up-to-date': notice('Already up to date', 'This build matches the cloud version.'); return
      case 'not-linked': notice('Not uploaded yet', 'This build has no cloud copy for this account. Upload it first.'); return
      case 'cloud-missing': notice('The cloud copy was deleted', 'Upload this build again to create a new cloud build.'); return
      case 'conflict': await openConflict(localId, outcome, null); return
      case 'error': notice('Something went wrong', outcome.message); return
    }
  }, [notice, onChanged, openConflict, requestSignIn, sync])

  const startLinkUpdate = useCallback(async (localId: string) => {
    const plan = await sync.planSharedLinkUpdate(localId)
    switch (plan.kind) {
      case 'sign-in-required': requestSignIn(); return
      case 'upload-first': notice('Upload first', 'Upload this build to the cloud, then update the shared link.'); return
      case 'conflict': await openConflict(localId, plan, null); return
      case 'confirm-link-update': setDialog({ kind: 'link-update', cloudBuildId: plan.cloudBuildId, revisionId: plan.revisionId }); return
    }
  }, [notice, openConflict, requestSignIn, sync])

  const run = async (fn: () => Promise<void>): Promise<void> => {
    setBusy(true)
    try { await fn() } finally { setBusy(false) }
  }

  const resolve = async (d: Extract<Dialog, { kind: 'conflict' }>, choice: 'keep-both' | 'keep-local' | 'keep-cloud', confirmed: boolean) => {
    await run(async () => {
      const outcome = await sync.resolveConflict(d.localId, d.conflict, choice, { confirmed })
      if (outcome.kind === 'conflict') {
        // The cloud changed again after the screen opened; show the new versions and replace nothing.
        await openConflict(d.localId, outcome, 'The cloud version changed again. Nothing was replaced; review the new version.')
        return
      }
      await showUpload(d.localId, outcome)
    })
  }

  let node: React.ReactNode = null
  if (dialog) {
    switch (dialog.kind) {
      case 'notice':
        node = <NoticeDialog title={dialog.title} body={dialog.body} actions={dialog.actions} onClose={close} />
        break
      case 'shorten':
        node = (
          <ShortenNameDialog
            currentName={dialog.currentName}
            suggested={dialog.suggested}
            onCancel={close}
            onConfirm={(name) => void run(async () => { await showUpload(dialog.localId, await sync.upload(dialog.localId, { confirmedName: name })) })}
          />
        )
        break
      case 'link-prompt':
        node = (
          <LinkPromptDialog
            cloudBuildName={dialog.cloudBuildName}
            onCancel={close}
            onLink={() => void run(async () => {
              await sync.linkExisting(dialog.localId, dialog.cloudBuildId)
              notice('Linked', 'This build is now linked to the cloud build.')
              onChanged()
            })}
            onUploadNew={() => void run(async () => { await showUpload(dialog.localId, await sync.upload(dialog.localId, { allowDuplicate: true })) })}
          />
        )
        break
      case 'conflict':
        node = (
          <ConflictDialog
            local={dialog.local}
            cloud={dialog.cloud}
            busy={busy}
            error={dialog.error}
            onCancel={close}
            onKeepBoth={() => void resolve(dialog, 'keep-both', false)}
            onKeepLocal={() => void resolve(dialog, 'keep-local', true)}
            onKeepCloud={() => void resolve(dialog, 'keep-cloud', true)}
          />
        )
        break
      case 'link-update':
        node = (
          <LinkUpdateDialog
            linkPath={linkPathFor(dialog.cloudBuildId)}
            onCancel={close}
            onConfirm={() => void run(async () => {
              try {
                await sync.confirmSharedLinkUpdate({ cloudBuildId: dialog.cloudBuildId, revisionId: dialog.revisionId })
                notice('Shared link updated', 'The link now shows this version.')
                onChanged()
              } catch (e) {
                notice('Could not update the link', e instanceof Error ? e.message : 'Try again.')
              }
            })}
          />
        )
        break
    }
  }

  return { dialog: node, startUpload, startDownload, startLinkUpdate, busy }
}
