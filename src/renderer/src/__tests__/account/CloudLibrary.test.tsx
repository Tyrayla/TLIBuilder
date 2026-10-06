import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { CloudLibraryView, type CloudLibraryActions } from '../../components/accounts/CloudLibraryOverlay'
import { AccountApiError, type CloudBuild } from '../../api/accounts'

vi.stubGlobal('window', new EventTarget())

const plain: CloudBuild = { cloudBuildId: 'cb1', name: 'Fire Mage', currentRevisionId: 'r1', semanticHash: 'h', updatedAt: 1_700_000_000, dataVersion: 's', namedLink: null }
const linked: CloudBuild = {
  ...plain, cloudBuildId: 'cb2', name: 'Ice Rogue',
  namedLink: { urlPath: '/u/tyra-4472/ice-rogue', slug: 'ice-rogue', listed: false, revisionId: 'r1' },
}

let renderer: TestRenderer.ReactTestRenderer | null = null
afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

const text = () => JSON.stringify(renderer!.toJSON())
const labels = () => renderer!.root.findAllByType('button').map((b) => b.children.join(''))
function click(label: string, index = 0) {
  const matches = renderer!.root.findAllByType('button').filter((x) => x.children.join('') === label)
  if (!matches[index]) throw new Error(`no button "${label}"; have ${labels().join(' | ')}`)
  return act(async () => { await matches[index].props.onClick() })
}

function actions(over: Partial<CloudLibraryActions> = {}): CloudLibraryActions {
  return {
    saveToDevice: vi.fn().mockResolvedValue(undefined),
    deleteBuild: vi.fn().mockResolvedValue(undefined),
    createLink: vi.fn().mockResolvedValue(undefined),
    setListed: vi.fn().mockResolvedValue(undefined),
    removeLink: vi.fn().mockResolvedValue(undefined),
    close: vi.fn(),
    ...over,
  }
}

function mount(builds: CloudBuild[] | null, a: CloudLibraryActions, extra: Partial<React.ComponentProps<typeof CloudLibraryView>> = {}) {
  act(() => {
    renderer = TestRenderer.create(
      <CloudLibraryView builds={builds} loading={false} loadError={null} usage={{ cloudBuilds: builds?.length ?? 0, limit: 20 }} actions={a} {...extra} />,
    )
  })
}

describe('CloudLibraryView', () => {
  it('lists cloud builds with the slot usage', () => {
    mount([plain, linked], actions())
    expect(text()).toContain('Fire Mage')
    expect(text()).toContain('Ice Rogue')
    expect(text()).toContain('2 of 20')
  })

  it('says so when the library is empty', () => {
    mount([], actions())
    expect(text()).toContain('No cloud builds yet')
  })

  it('saves a cloud build to this device as a new local build', async () => {
    const a = actions()
    mount([plain], a)
    await click('Save to this device')
    expect(a.saveToDevice).toHaveBeenCalledWith('cb1')
  })

  it('delete asks first and names the link that will stop working', async () => {
    const a = actions()
    mount([linked], a)
    await click('Delete from cloud')
    expect(a.deleteBuild).not.toHaveBeenCalled()
    expect(text()).toContain('/u/tyra-4472/ice-rogue')
    expect(text()).toContain('will stop working')
    await click('Delete build and link')
    expect(a.deleteBuild).toHaveBeenCalledWith('cb2')
  })

  it('delete of an unlinked build still asks first', async () => {
    const a = actions()
    mount([plain], a)
    await click('Delete from cloud')
    expect(a.deleteBuild).not.toHaveBeenCalled()
    await click('Delete build')
    expect(a.deleteBuild).toHaveBeenCalledWith('cb1')
  })

  it('cancelling the delete changes nothing', async () => {
    const a = actions()
    mount([plain], a)
    await click('Delete from cloud')
    await click('Cancel')
    expect(a.deleteBuild).not.toHaveBeenCalled()
  })

  it('creates a named link, unlisted by default, with an optional slug', async () => {
    const a = actions()
    mount([plain], a)
    act(() => { renderer!.root.findByProps({ 'aria-label': 'Link name for Fire Mage' }).props.onChange({ target: { value: 'fire-mage' } }) })
    await click('Create link')
    expect(a.createLink).toHaveBeenCalledWith('cb1', 'fire-mage')
  })

  it('blocks an invalid slug before calling the service', async () => {
    const a = actions()
    mount([plain], a)
    act(() => { renderer!.root.findByProps({ 'aria-label': 'Link name for Fire Mage' }).props.onChange({ target: { value: '-Bad Slug-' } }) })
    await click('Create link')
    expect(a.createLink).not.toHaveBeenCalled()
    expect(text()).toContain('1–48')
  })

  it('shows an unlisted link and lets the owner list it on the profile', async () => {
    const a = actions()
    mount([linked], a)
    expect(text()).toContain('/u/tyra-4472/ice-rogue')
    expect(text()).toContain('Unlisted')
    await click('Show on profile')
    expect(a.setListed).toHaveBeenCalledWith('cb2', true)
  })

  it('reports the 10-build profile limit in plain words', async () => {
    const a = actions({ setListed: vi.fn().mockRejectedValue(new AccountApiError(409, 'profile_quota_reached', 'x')) })
    mount([linked], a)
    await click('Show on profile')
    expect(text()).toContain('10')
    expect(text()).toContain('profile')
  })

  it('a taken slug is explained', async () => {
    const a = actions({ createLink: vi.fn().mockRejectedValue(new AccountApiError(409, 'slug_taken', 'x')) })
    mount([plain], a)
    act(() => { renderer!.root.findByProps({ 'aria-label': 'Link name for Fire Mage' }).props.onChange({ target: { value: 'taken' } }) })
    await click('Create link')
    expect(text()).toContain('already used')
  })

  it('removes a link without deleting the build', async () => {
    const a = actions()
    mount([linked], a)
    await click('Remove link')
    expect(a.removeLink).toHaveBeenCalledWith('cb2')
    expect(a.deleteBuild).not.toHaveBeenCalled()
  })

  it('renders names as text only', () => {
    mount([{ ...plain, name: '<script>alert(1)</script>' }], actions())
    expect(renderer!.root.findAll((n) => n.props?.dangerouslySetInnerHTML !== undefined)).toHaveLength(0)
    expect(text()).toContain('<script>alert(1)</script>')
  })

  it('shows a load error and a loading state', () => {
    mount(null, actions(), { loadError: 'The account service could not be reached.' })
    expect(text()).toContain('could not be reached')
    act(() => { renderer!.unmount() })
    mount(null, actions(), { loading: true })
    expect(text()).toContain('Loading')
  })
})
