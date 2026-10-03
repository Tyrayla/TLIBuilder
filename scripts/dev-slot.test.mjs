import { describe, it, expect } from 'vitest'
import { portsFor, MAX_SLOTS } from './dev-slot.mjs'

const PORT_KEYS = ['backendPort', 'webPort', 'e2eBackendPort', 'e2eWebPort', 'vitePort', 'cdpPort']
// Fixed ports the app and E2E use when no slot is set (src/main 8765/8766, e2e 8800/8801, vite 5173, CDP default 9222).
const FIXED_DEFAULTS = [8765, 8766, 8800, 8801, 5173, 9222]

describe('dev-slot port allocation', () => {
  it('gives every port of every claimable slot a unique number (no two worktrees can collide)', () => {
    const seen = new Map()
    for (let slot = 1; slot <= MAX_SLOTS; slot++) {
      const p = portsFor(slot)
      for (const k of PORT_KEYS) {
        const owner = seen.get(p[k])
        expect(owner, `port ${p[k]} used by ${owner} and slot ${slot} ${k}`).toBeUndefined()
        seen.set(p[k], `slot ${slot} ${k}`)
      }
    }
    expect(seen.size).toBe(MAX_SLOTS * PORT_KEYS.length)
  })

  it('never hands out a port the unslotted app or E2E uses by default', () => {
    for (let slot = 1; slot <= MAX_SLOTS; slot++) {
      const p = portsFor(slot)
      for (const k of PORT_KEYS) expect(FIXED_DEFAULTS).not.toContain(p[k])
    }
  })

  it('gives two checkouts that hold the same slot number (one after the other) different scratch dirs', () => {
    const a = portsFor(3, 'C:\\umbrella\\worktrees\\alpha')
    const b = portsFor(3, 'C:\\umbrella\\worktrees\\beta')
    expect(a.backendPort).toBe(b.backendPort)
    expect(a.userData).not.toBe(b.userData)
    expect(portsFor(3, 'C:\\umbrella\\worktrees\\alpha').userData).toBe(a.userData)
  })

  it('maps slot 1 to the documented ports', () => {
    expect(portsFor(1)).toMatchObject({
      backendPort: 8811, webPort: 8841, e2eBackendPort: 8871, e2eWebPort: 8901, vitePort: 5174, cdpPort: 9223,
    })
  })
})
