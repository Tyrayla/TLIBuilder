import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import ConflictDialog, { type ConflictSide } from '../../components/accounts/ConflictDialog'

vi.stubGlobal('window', new EventTarget())

const local: ConflictSide = { name: 'Fire Mage (local)', savedAt: 1_700_000_000, hero: 'Rehan', mainSkill: 'Chain Lightning' }
const cloud: ConflictSide = { name: 'Fire Mage (cloud)', savedAt: 1_700_100_000, hero: 'Rehan', mainSkill: 'Ice Bolt' }

let renderer: TestRenderer.ReactTestRenderer | null = null
afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

function mount(over: Partial<React.ComponentProps<typeof ConflictDialog>> = {}) {
  const handlers = { onKeepBoth: vi.fn(), onKeepLocal: vi.fn(), onKeepCloud: vi.fn(), onCancel: vi.fn() }
  act(() => { renderer = TestRenderer.create(<ConflictDialog local={local} cloud={cloud} busy={false} error={null} {...handlers} {...over} />) })
  return handlers
}

const text = (): string => JSON.stringify(renderer!.toJSON())
function button(label: string) {
  const found = renderer!.root.findAllByType('button').find((b) => b.children.join('') === label)
  if (!found) throw new Error(`no button "${label}" in ${text()}`)
  return found
}
const labels = () => renderer!.root.findAllByType('button').map((b) => b.children.join(''))

describe('ConflictDialog', () => {
  it('shows both versions side by side with name, saved date, hero and main skill', () => {
    mount()
    const t = text()
    for (const part of ['Fire Mage (local)', 'Fire Mage (cloud)', 'Rehan', 'Chain Lightning', 'Ice Bolt']) {
      expect(t).toContain(part)
    }
    expect(t).toContain(new Date(1_700_000_000 * 1000).toLocaleDateString())
  })

  it('offers Keep both as the highlighted default and runs it without a second confirmation', () => {
    const h = mount()
    expect(labels()).toEqual(expect.arrayContaining(['Keep both', 'Keep local', 'Keep cloud', 'Cancel']))
    expect(button('Keep both').props.className).toContain('btn-primary')
    expect(button('Keep local').props.className).not.toContain('btn-primary')
    act(() => { button('Keep both').props.onClick() })
    expect(h.onKeepBoth).toHaveBeenCalledTimes(1)
  })

  it('Keep local asks again, naming the cloud version it will replace, and only then acts', () => {
    const h = mount()
    act(() => { button('Keep local').props.onClick() })
    expect(h.onKeepLocal).not.toHaveBeenCalled()
    expect(text()).toContain('Fire Mage (cloud)')
    expect(text().toLowerCase()).toContain('replace')
    act(() => { button('Replace cloud version').props.onClick() })
    expect(h.onKeepLocal).toHaveBeenCalledTimes(1)
  })

  it('Keep cloud asks again, naming the local build it will replace, and only then acts', () => {
    const h = mount()
    act(() => { button('Keep cloud').props.onClick() })
    expect(h.onKeepCloud).not.toHaveBeenCalled()
    expect(text()).toContain('Fire Mage (local)')
    act(() => { button('Replace local build').props.onClick() })
    expect(h.onKeepCloud).toHaveBeenCalledTimes(1)
  })

  it('Back from the confirmation returns to the choices without acting', () => {
    const h = mount()
    act(() => { button('Keep local').props.onClick() })
    act(() => { button('Back').props.onClick() })
    expect(labels()).toContain('Keep both')
    expect(h.onKeepLocal).not.toHaveBeenCalled()
  })

  it('Cancel changes nothing', () => {
    const h = mount()
    act(() => { button('Cancel').props.onClick() })
    expect(h.onCancel).toHaveBeenCalledTimes(1)
    expect(h.onKeepBoth).not.toHaveBeenCalled()
  })

  it('disables the actions while busy and shows a service error', () => {
    mount({ busy: true, error: 'The cloud version changed again.' })
    expect(button('Keep both').props.disabled).toBe(true)
    expect(text()).toContain('The cloud version changed again.')
  })

  it('renders names as text, never as HTML', () => {
    mount({ local: { ...local, name: '<img src=x onerror=alert(1)>' } })
    expect(renderer!.root.findAll((n) => n.props?.dangerouslySetInnerHTML !== undefined)).toHaveLength(0)
    expect(text()).toContain('<img src=x onerror=alert(1)>')
  })
})
