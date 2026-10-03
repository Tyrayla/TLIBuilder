import { describe, it, expect } from 'vitest'
import { spawn } from 'child_process'
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync, utimesSync } from 'fs'
import { tmpdir } from 'os'
import path from 'path'
import { fileURLToPath } from 'url'

const SCRIPT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dev-slot.mjs')

function info(env) {
  return new Promise((resolve, reject) => {
    const p = spawn(process.execPath, [SCRIPT, 'info'], { env: { ...process.env, ...env } })
    let out = ''
    p.stdout.on('data', d => { out += d })
    p.on('exit', code => (code === 0 ? resolve(JSON.parse(out)) : reject(new Error(`exit ${code}`))))
  })
}

describe('dev-slot claiming', () => {
  it('reclaims a slot whose registry file is empty and old (a claim that crashed mid-write)', async () => {
    const tmp = mkdtempSync(path.join(tmpdir(), 'slot-claim-'))
    const env = { TLI_SLOTS_DIR: path.join(tmp, 'slots'), TLI_SLOT_FILE: path.join(tmp, 'local.json') }
    try {
      mkdirSync(env.TLI_SLOTS_DIR, { recursive: true })
      const stale = path.join(env.TLI_SLOTS_DIR, '1.json')
      writeFileSync(stale, '')
      const twoMinutesAgo = new Date(Date.now() - 120_000)
      utimesSync(stale, twoMinutesAgo, twoMinutesAgo)
      const got = await info(env)
      expect(got.slot).toBe(1)
      expect(readdirSync(env.TLI_SLOTS_DIR)).toEqual(['1.json'])
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  }, 30000)

  it('treats a valid-JSON but malformed entry ({}) as unreadable instead of crashing, and reclaims it when old', async () => {
    const tmp = mkdtempSync(path.join(tmpdir(), 'slot-claim-'))
    const env = { TLI_SLOTS_DIR: path.join(tmp, 'slots'), TLI_SLOT_FILE: path.join(tmp, 'local.json') }
    try {
      mkdirSync(env.TLI_SLOTS_DIR, { recursive: true })
      const bad = path.join(env.TLI_SLOTS_DIR, '1.json')
      writeFileSync(bad, '{}')
      const old = new Date(Date.now() - 120_000)
      utimesSync(bad, old, old)
      const got = await info(env)
      expect(got.slot).toBe(1)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  }, 30000)

  it('breaks a lock whose owner process is dead, and never breaks one whose owner is alive', async () => {
    const tmp = mkdtempSync(path.join(tmpdir(), 'slot-claim-'))
    const env = { TLI_SLOTS_DIR: path.join(tmp, 'slots'), TLI_SLOT_FILE: path.join(tmp, 'local.json'), TLI_SLOT_LOCK_WAIT_MS: '1500' }
    const lock = path.join(env.TLI_SLOTS_DIR, '.lock')
    try {
      mkdirSync(lock, { recursive: true })
      // Owner alive (this test process), held for longer than the wait: the claim must give up, not steal it.
      writeFileSync(path.join(lock, 'owner'), `${process.pid} live-token`)
      await expect(info(env)).rejects.toThrow(/exit 1/)
      expect(readFileSync(path.join(lock, 'owner'), 'utf8')).toBe(`${process.pid} live-token`)
      // Owner dead (a pid that cannot exist): the claim breaks the lock and succeeds.
      writeFileSync(path.join(lock, 'owner'), '2147483646 dead-token')
      const got = await info(env)
      expect(got.slot).toBe(1)
      expect(readdirSync(env.TLI_SLOTS_DIR).filter(n => n.startsWith('.lock'))).toEqual([])
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  }, 30000)

  it('recovers an ownerless lock (a release killed mid-cleanup) once it is a few seconds old', async () => {
    const tmp = mkdtempSync(path.join(tmpdir(), 'slot-claim-'))
    const env = { TLI_SLOTS_DIR: path.join(tmp, 'slots'), TLI_SLOT_FILE: path.join(tmp, 'local.json'), TLI_SLOT_LOCK_WAIT_MS: '3000' }
    try {
      const lock = path.join(env.TLI_SLOTS_DIR, '.lock')
      mkdirSync(lock, { recursive: true })
      const old = new Date(Date.now() - 60_000)
      utimesSync(lock, old, old)
      const got = await info(env)
      expect(got.slot).toBe(1)
      expect(readdirSync(env.TLI_SLOTS_DIR).filter(n => n.startsWith('.lock'))).toEqual([])
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  }, 30000)

  it('ignores a remembered slot 0 (the unslotted default ports) and claims a real slot', async () => {
    const tmp = mkdtempSync(path.join(tmpdir(), 'slot-claim-'))
    const env = { TLI_SLOTS_DIR: path.join(tmp, 'slots'), TLI_SLOT_FILE: path.join(tmp, 'local.json') }
    try {
      mkdirSync(env.TLI_SLOTS_DIR, { recursive: true })
      writeFileSync(env.TLI_SLOT_FILE, JSON.stringify({ slot: 0 }))
      writeFileSync(path.join(env.TLI_SLOTS_DIR, '0.json'), JSON.stringify({ path: path.resolve(path.dirname(SCRIPT), '..') }))
      const got = await info(env)
      expect(got.slot).toBe(1)
      expect(got.vitePort).toBe(5174)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  }, 30000)

  it('concurrent claims from one checkout end with exactly one registry entry for it', async () => {
    const tmp = mkdtempSync(path.join(tmpdir(), 'slot-claim-'))
    const env = { TLI_SLOTS_DIR: path.join(tmp, 'slots'), TLI_SLOT_FILE: path.join(tmp, 'local.json') }
    try {
      const results = await Promise.all(Array.from({ length: 6 }, () => info(env)))
      const slotsHeld = readdirSync(env.TLI_SLOTS_DIR)
      expect(slotsHeld).toHaveLength(1)
      const local = JSON.parse(readFileSync(env.TLI_SLOT_FILE, 'utf8'))
      expect(slotsHeld[0]).toBe(`${local.slot}.json`)
      // every process may have seen a different interim slot, but the survivor is the one on disk
      expect(results.map(r => r.slot)).toContain(local.slot)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  }, 30000)
})
