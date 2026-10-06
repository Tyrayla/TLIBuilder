import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import zlib from 'node:zlib'
import TestRenderer, { act } from 'react-test-renderer'
import { summarizeCode } from '../../utils/buildSummary'
import { ShortenNameDialog, LinkPromptDialog, LinkUpdateDialog } from '../../components/accounts/CloudDialogs'
import { useCloudActions } from '../../components/accounts/useCloudActions'
import type { CloudSync, ConflictOutcome } from '../../utils/cloudSync'
import type { CloudBuild } from '../../api/accounts'

vi.stubGlobal('window', new EventTarget())

function codeOf(obj: unknown): string {
  const deflated = zlib.deflateSync(Buffer.from(JSON.stringify(obj), 'utf-8'), { level: 9 })
  return `tli1_${deflated.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`
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

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 30)) })

describe('summarizeCode', () => {
  it('reads the hero and the first active skill from a code', async () => {
    const code = codeOf({
      v: 2, traitId: 't1',
      skills: [
        { slot: 6, name: 'Aura', item_id: 'a' },
        { slot: 2, name: 'Chain Lightning', item_id: 'c' },
        { slot: 1, name: 'Ice Bolt', item_id: 'i' },
      ],
    })
    const s = await summarizeCode(code, [{ trait_id: 't1', hero: 'Rehan', variant_name: 'Berserker' }] as never)
    expect(s).toEqual({ hero: 'Rehan · Berserker', mainSkill: 'Ice Bolt' })
  })

  it('degrades to nulls for an unknown trait and no skills', async () => {
    expect(await summarizeCode(codeOf({ v: 2 }), null)).toEqual({ hero: null, mainSkill: null })
  })

  it('degrades to nulls for a code it cannot read', async () => {
    expect(await summarizeCode('garbage', null)).toEqual({ hero: null, mainSkill: null })
  })
})

describe('ShortenNameDialog', () => {
  it('pre-fills the first 50 characters and never submits a longer name', async () => {
    const onConfirm = vi.fn()
    act(() => { renderer = TestRenderer.create(<ShortenNameDialog currentName={'n'.repeat(60)} suggested={'n'.repeat(50)} onConfirm={onConfirm} onCancel={vi.fn()} />) })
    const input = renderer!.root.findByType('input')
    expect(input.props.value).toBe('n'.repeat(50))
    expect(input.props.maxLength).toBe(50)
    await click('Rename and upload')
    expect(onConfirm).toHaveBeenCalledWith('n'.repeat(50))
  })

  it('does not accept an empty name', async () => {
    const onConfirm = vi.fn()
    act(() => { renderer = TestRenderer.create(<ShortenNameDialog currentName="x" suggested="x" onConfirm={onConfirm} onCancel={vi.fn()} />) })
    act(() => { renderer!.root.findByType('input').props.onChange({ target: { value: '   ' } }) })
    const button = renderer!.root.findAllByType('button').find((b) => b.children.join('') === 'Rename and upload')!
    expect(button.props.disabled).toBe(true)
  })
})

describe('LinkPromptDialog', () => {
  it('offers Link, Upload as a new build, and Cancel, naming the existing build', async () => {
    const h = { onLink: vi.fn(), onUploadNew: vi.fn(), onCancel: vi.fn() }
    act(() => { renderer = TestRenderer.create(<LinkPromptDialog cloudBuildName="Fire Mage" {...h} />) })
    expect(text()).toContain('Fire Mage')
    expect(text()).toContain('20')
    await click('Link to “Fire Mage”')
    await click('Upload as a new build')
    await click('Cancel')
    expect(h.onLink).toHaveBeenCalledTimes(1)
    expect(h.onUploadNew).toHaveBeenCalledTimes(1)
    expect(h.onCancel).toHaveBeenCalledTimes(1)
  })
})

describe('LinkUpdateDialog', () => {
  it('moves the link only after the explicit confirmation', async () => {
    const h = { onConfirm: vi.fn(), onCancel: vi.fn() }
    act(() => { renderer = TestRenderer.create(<LinkUpdateDialog linkPath="/u/tyra-4472/fire" {...h} />) })
    expect(text()).toContain('/u/tyra-4472/fire')
    expect(h.onConfirm).not.toHaveBeenCalled()
    await click('Update shared link')
    expect(h.onConfirm).toHaveBeenCalledTimes(1)
  })
})

// ── Controller hook ─────────────────────────────────────────────────────────
const CLOUD: CloudBuild = {
  cloudBuildId: 'cb1', name: 'Fire', currentRevisionId: 'r1', semanticHash: 'h', updatedAt: 1, dataVersion: 's', namedLink: null,
}

function conflict(): ConflictOutcome {
  return {
    kind: 'conflict', cloudBuildId: 'cb1', cloudRevisionId: 'r2', defaultChoice: 'keep-both',
    cloud: { build: { ...CLOUD, currentRevisionId: 'r2', updatedAt: 1_700_000_000 }, code: codeOf({ v: 2, name: 'Fire' }) },
    local: { name: 'Fire local', code: codeOf({ v: 2, name: 'Fire local' }) },
  }
}

function fakeSync(over: Partial<Record<keyof CloudSync, unknown>> = {}): CloudSync {
  return {
    upload: vi.fn().mockResolvedValue({ kind: 'uploaded', build: CLOUD }),
    linkExisting: vi.fn().mockResolvedValue(undefined),
    resolveConflict: vi.fn().mockResolvedValue({ kind: 'kept-both', newLocalBuildId: 'N' }),
    download: vi.fn().mockResolvedValue({ kind: 'downloaded' }),
    downloadCloudBuild: vi.fn(),
    planSharedLinkUpdate: vi.fn().mockResolvedValue({ kind: 'confirm-link-update', cloudBuildId: 'cb1', revisionId: 'r1' }),
    confirmSharedLinkUpdate: vi.fn().mockResolvedValue({}),
    onLocalBuildDeleted: vi.fn(),
    ...over,
  } as unknown as CloudSync
}

function Harness({ sync, onChanged, signIn, linkPathFor }: {
  sync: CloudSync; onChanged: () => void; signIn: () => void; linkPathFor: (id: string) => string | null
}) {
  const cloud = useCloudActions({ sync, onChanged, requestSignIn: signIn, linkPathFor, heroTraits: null })
  return (
    <div>
      <button onClick={() => cloud.startUpload('L1')}>upload</button>
      <button onClick={() => cloud.startDownload('L1')}>download</button>
      <button onClick={() => cloud.startLinkUpdate('L1')}>link</button>
      {cloud.dialog}
    </div>
  )
}

function mountHarness(sync: CloudSync) {
  const onChanged = vi.fn()
  const signIn = vi.fn()
  act(() => { renderer = TestRenderer.create(<Harness sync={sync} onChanged={onChanged} signIn={signIn} linkPathFor={() => '/u/tyra-4472/fire'} />) })
  return { onChanged, signIn }
}

describe('useCloudActions', () => {
  it('a plain upload shows a confirmation notice and refreshes the library', async () => {
    const sync = fakeSync()
    const { onChanged } = mountHarness(sync)
    await click('upload')
    expect(sync.upload).toHaveBeenCalledWith('L1', {})
    expect(text()).toContain('Uploaded')
    expect(onChanged).toHaveBeenCalled()
  })

  it('asks the user to sign in instead of failing silently', async () => {
    const { signIn } = mountHarness(fakeSync({ upload: vi.fn().mockResolvedValue({ kind: 'sign-in-required' }) }))
    await click('upload')
    expect(signIn).toHaveBeenCalled()
  })

  it('name too long: asks for a shorter name, then uploads with the confirmed name', async () => {
    const upload = vi.fn()
      .mockResolvedValueOnce({ kind: 'shorten-name', suggestedName: 'short', currentName: 'a much longer name' })
      .mockResolvedValue({ kind: 'uploaded', build: CLOUD })
    const sync = fakeSync({ upload })
    mountHarness(sync)
    await click('upload')
    expect(text()).toContain('Rename and upload')
    await click('Rename and upload')
    expect(upload).toHaveBeenLastCalledWith('L1', { confirmedName: 'short' })
  })

  it('a content match asks Link / New / Cancel and acts only on the choice', async () => {
    const upload = vi.fn()
      .mockResolvedValueOnce({ kind: 'link-prompt', cloudBuildId: 'cb9', cloudBuildName: 'Existing' })
      .mockResolvedValue({ kind: 'uploaded', build: CLOUD })
    const sync = fakeSync({ upload })
    mountHarness(sync)
    await click('upload')
    expect(sync.linkExisting).not.toHaveBeenCalled()
    await click('Upload as a new build')
    expect(upload).toHaveBeenLastCalledWith('L1', { allowDuplicate: true })
  })

  it('Link creates the link and nothing else', async () => {
    const upload = vi.fn().mockResolvedValue({ kind: 'link-prompt', cloudBuildId: 'cb9', cloudBuildName: 'Existing' })
    const sync = fakeSync({ upload })
    mountHarness(sync)
    await click('upload')
    await click('Link to “Existing”')
    expect(sync.linkExisting).toHaveBeenCalledWith('L1', 'cb9')
    expect(upload).toHaveBeenCalledTimes(1)
  })

  it('a conflict opens the conflict screen, and Keep both resolves without a second confirmation', async () => {
    const sync = fakeSync({ upload: vi.fn().mockResolvedValue(conflict()) })
    const { onChanged } = mountHarness(sync)
    await click('upload')
    expect(text()).toContain('changed in two places')
    await click('Keep both')
    expect(sync.resolveConflict).toHaveBeenCalledWith('L1', expect.objectContaining({ kind: 'conflict' }), 'keep-both', { confirmed: false })
    expect(onChanged).toHaveBeenCalled()
  })

  it('Keep local only runs after the second confirmation and is sent as confirmed', async () => {
    const sync = fakeSync({
      upload: vi.fn().mockResolvedValue(conflict()),
      resolveConflict: vi.fn().mockResolvedValue({ kind: 'uploaded', build: CLOUD }),
    })
    mountHarness(sync)
    await click('upload')
    await click('Keep local')
    expect(sync.resolveConflict).not.toHaveBeenCalled()
    await click('Replace cloud version')
    expect(sync.resolveConflict).toHaveBeenCalledWith('L1', expect.anything(), 'keep-local', { confirmed: true })
  })

  it('a conflict raised again while resolving swaps in the new versions and shows no replacement', async () => {
    const again = { ...conflict(), cloudRevisionId: 'r3' }
    const sync = fakeSync({
      upload: vi.fn().mockResolvedValue(conflict()),
      resolveConflict: vi.fn().mockResolvedValue(again),
    })
    mountHarness(sync)
    await click('upload')
    await click('Keep local')
    await click('Replace cloud version')
    await settle()
    expect(text()).toContain('changed in two places')
    expect(text()).toContain('changed again')
  })

  it('download over local changes goes to the conflict screen, never silently replaces', async () => {
    const sync = fakeSync({ download: vi.fn().mockResolvedValue(conflict()) })
    mountHarness(sync)
    await click('download')
    expect(text()).toContain('changed in two places')
  })

  it('shared link update waits for the explicit confirmation', async () => {
    const sync = fakeSync()
    mountHarness(sync)
    await click('link')
    expect(sync.confirmSharedLinkUpdate).not.toHaveBeenCalled()
    expect(text()).toContain('/u/tyra-4472/fire')
    await click('Update shared link')
    expect(sync.confirmSharedLinkUpdate).toHaveBeenCalledWith({ cloudBuildId: 'cb1', revisionId: 'r1' })
  })

  it('reports the 20-build limit in plain words', async () => {
    mountHarness(fakeSync({ upload: vi.fn().mockResolvedValue({ kind: 'quota-reached' }) }))
    await click('upload')
    expect(text()).toContain('20')
  })

  it('reports a newer cloud version and points at download', async () => {
    mountHarness(fakeSync({ upload: vi.fn().mockResolvedValue({ kind: 'cloud-newer' }) }))
    await click('upload')
    expect(text().toLowerCase()).toContain('download')
  })

  it('surfaces service errors as text', async () => {
    mountHarness(fakeSync({ upload: vi.fn().mockResolvedValue({ kind: 'error', code: 'network_error', message: 'The account service could not be reached.' }) }))
    await click('upload')
    expect(text()).toContain('could not be reached')
  })
})
