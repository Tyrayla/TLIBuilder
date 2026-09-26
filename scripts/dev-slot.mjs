// Per-worktree dev "slot": one isolated set of ports + dirs per checkout, so several worktrees (and the
// agents driving them) can run the app side by side without port-killing each other's backend.
//
//   node scripts/dev-slot.mjs info          print this checkout's slot + ports as JSON (claims a slot if needed)
//   node scripts/dev-slot.mjs electron      electron-vite dev on the slot's ports, CDP open for agent-browser
//   node scripts/dev-slot.mjs web           serve the built dist-web on the slot's web port (npm run build:web first)
//   node scripts/dev-slot.mjs e2e [args]    playwright on the slot's E2E ports (build first, like test:e2e does)
//   node scripts/dev-slot.mjs release       give this checkout's slot back
//
// Slots are claimed in <umbrella>/shared/slots/<N>.json (found via the .tli-umbrella marker, same as the
// claims ledger), lowest free N >= 1; a slot whose recorded checkout no longer exists is reclaimed. The
// checkout remembers its slot in a gitignored .tli-slot.json. Dev-only: the env overrides it sets are
// ignored by a packaged build (src/main/index.ts), and CDP is only opened through electron-vite dev.
import { spawn, spawnSync, execFileSync } from 'child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync, linkSync, statSync, unlinkSync, cpSync, rmdirSync, renameSync } from 'fs'
import { tmpdir } from 'os'
import path from 'path'
import { createHash } from 'crypto'
import { fileURLToPath, pathToFileURL } from 'url'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// TLI_SLOT_FILE / TLI_SLOTS_DIR exist for tests; normal use never sets them.
const LOCAL_FILE = process.env.TLI_SLOT_FILE || path.join(REPO, '.tli-slot.json')
const MODES = ['info', 'electron', 'web', 'e2e', 'release']

// Each port family gets its own band of BAND ports; a slot N uses base + N. Slots must stay below BAND
// or one family's band runs into the next (slot 21 web == slot 1 e2e-backend with the old 20-wide
// bands). Bases also avoid the fixed defaults: 8765/8766 (backend), 8800/8801 (E2E), 5173, 9222.
export const BAND = 30
export const MAX_SLOTS = BAND - 1

export function portsFor(slot, repo = REPO) {
  // Scratch dirs are keyed by slot AND checkout, so a checkout that later reuses slot N never inherits
  // the previous holder's app state.
  const key = createHash('sha1').update(path.resolve(repo).toLowerCase()).digest('hex').slice(0, 8)
  return {
    slot,
    backendPort: 8810 + slot,
    webPort: 8810 + BAND + slot,
    e2eBackendPort: 8810 + 2 * BAND + slot,
    e2eWebPort: 8810 + 3 * BAND + slot,
    vitePort: 5173 + slot,
    cdpPort: 9222 + slot,
    userData: path.join(tmpdir(), `tli-slot-${slot}-${key}`, 'userData'),
    scratch: path.join(tmpdir(), `tli-slot-${slot}-${key}`),
  }
}

function slotsDir() {
  if (process.env.TLI_SLOTS_DIR) return process.env.TLI_SLOTS_DIR
  let dir = REPO
  for (;;) {
    if (existsSync(path.join(dir, '.tli-umbrella'))) return path.join(dir, 'shared', 'slots')
    const up = path.dirname(dir)
    if (up === dir) return path.join(tmpdir(), 'tli-slots')   // no umbrella: machine-local registry
    dir = up
  }
}

const samePath = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()

function readJson(file) {
  try { return JSON.parse(readFileSync(file, 'utf8')) } catch { return null }
}

// A registry entry counts only if it names a checkout path; anything else (empty, {}, garbage) is unreadable.
function readReg(file) {
  const reg = readJson(file)
  return reg && typeof reg.path === 'string' && reg.path ? reg : null
}

// Every read-decide-write on the registry happens under one lock with an owner identity:
//  - acquire: build `.lock.<token>/owner` (pid + token), then rename it to `.lock`. The rename fails
//    while another (non-empty) `.lock` exists, so exactly one process holds it, and the owner file is
//    there from the first instant anyone can see the lock.
//  - break: only when the owning PROCESS is dead (a live holder that is merely slow is never broken).
//    The breaker renames `.lock` aside first and checks the moved lock is the dead owner's; if a live
//    process's fresh lock was grabbed instead, it is put back.
//  - release: a holder removes `.lock` only if it still carries its own token.
const sleepMs = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)

function lockOwner(lockDir) {
  try { const [pid, token] = readFileSync(path.join(lockDir, 'owner'), 'utf8').trim().split(' '); return { pid: Number(pid), token } } catch { return null }
}
function pidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try { process.kill(pid, 0); return true } catch (e) { return e.code === 'EPERM' }
}
function removeLockDir(d) { try { unlinkSync(path.join(d, 'owner')) } catch { /* none */ } try { rmdirSync(d) } catch { /* gone */ } }

function withLock(dir, fn) {
  const lock = path.join(dir, '.lock')
  const token = `${process.pid}-${Math.random().toString(36).slice(2)}`
  const mine = path.join(dir, `.lock.${token}`)
  const deadline = Date.now() + Number(process.env.TLI_SLOT_LOCK_WAIT_MS || 20_000)
  for (;;) {
    mkdirSync(mine, { recursive: true })
    writeFileSync(path.join(mine, 'owner'), `${process.pid} ${token}`)
    try { renameSync(mine, lock); break } catch { removeLockDir(mine) }
    const seen = lockOwner(lock)
    // An ownerless .lock can only be a half-finished removal (the owner file exists before the lock
    // does), so after a short grace it is as dead as a crashed holder's.
    let ownerless = false
    if (!seen) { try { ownerless = Date.now() - statSync(lock).mtimeMs > 5_000 } catch { continue } }
    if (ownerless || (seen && !pidAlive(seen.pid))) {       // holder crashed: break its lock, safely
      const aside = path.join(dir, `.lock.broken.${token}`)
      try {
        renameSync(lock, aside)
        const moved = lockOwner(aside)
        if (ownerless ? !moved : (moved && moved.token === seen.token)) removeLockDir(aside)
        else { try { renameSync(aside, lock) } catch { removeLockDir(aside) } }
      } catch { /* someone else moved it first */ }
      continue
    }
    if (Date.now() > deadline) throw new Error(`dev-slot registry lock busy: ${lock} (held by pid ${seen?.pid ?? '?'})`)
    sleepMs(50)
  }
  try { return fn() } finally {
    // Move our lock aside atomically first, so a kill mid-cleanup can never leave an ownerless .lock.
    if (lockOwner(lock)?.token === token) {
      const done = path.join(dir, `.lock.done.${token}`)
      try { renameSync(lock, done); removeLockDir(done) } catch { /* already gone */ }
    }
  }
}

// A registry entry is published atomically (write a temp file, then hard-link it into place: link()
// fails if the name exists), so no reader ever sees a half-written claim. An unreadable entry can only
// be a crash leftover from an older version: treat it as in-flight for a minute, then reclaim it.
const STALE_UNREADABLE_MS = 60_000

function publish(file, content) {
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`
  writeFileSync(tmp, content)
  try { linkSync(tmp, file); return true } catch { return false } finally { try { unlinkSync(tmp) } catch { /* gone */ } }
}

function unreadableAndOld(file) {
  try { return Date.now() - statSync(file).mtimeMs > STALE_UNREADABLE_MS } catch { return false }
}

function claimSlot() {
  const dir = slotsDir()
  mkdirSync(dir, { recursive: true })
  return withLock(dir, () => claimLocked(dir))
}

function claimLocked(dir) {
  const local = readJson(LOCAL_FILE)
  let mine = null
  if (local && Number.isInteger(local.slot) && local.slot >= 1 && local.slot <= MAX_SLOTS) {
    const reg = readReg(path.join(dir, `${local.slot}.json`))
    if (reg && samePath(reg.path, REPO)) mine = local.slot
  }
  for (let n = 1; mine === null && n <= MAX_SLOTS; n++) {
    const file = path.join(dir, `${n}.json`)
    const reg = readReg(file)
    if (reg && samePath(reg.path, REPO)) { mine = n; break }
    if (reg && existsSync(reg.path)) continue                    // held by a live checkout
    if (!reg && existsSync(file) && !unreadableAndOld(file)) continue   // someone's claim in flight
    if (existsSync(file)) { try { unlinkSync(file) } catch { continue } } // stale: checkout gone, or crash leftover
    if (publish(file, JSON.stringify({ path: REPO, claimedAt: new Date().toISOString() }, null, 2))) mine = n
  }
  if (mine === null) throw new Error(`no free dev slot in ${dir} (all ${MAX_SLOTS} held by existing checkouts)`)
  // Concurrent claims from this same checkout may each have won a slot: keep the lowest, free the rest.
  for (let n = 1; n <= MAX_SLOTS; n++) {
    if (n === mine) continue
    const file = path.join(dir, `${n}.json`)
    const reg = readReg(file)
    if (reg && samePath(reg.path, REPO)) { try { unlinkSync(file) } catch { /* already gone */ } }
  }
  return remember(mine)
}

function remember(slot) {
  writeFileSync(LOCAL_FILE, JSON.stringify(portsFor(slot), null, 2) + '\n')
  return slot
}

function release() {
  const local = readJson(LOCAL_FILE)
  if (!local) { console.log('no slot claimed here'); return }
  const dir = slotsDir()
  mkdirSync(dir, { recursive: true })
  withLock(dir, () => {
    const file = path.join(dir, `${local.slot}.json`)
    const reg = readReg(file)
    if (reg && samePath(reg.path, REPO)) unlinkSync(file)
  })
  unlinkSync(LOCAL_FILE)
  console.log(`released slot ${local.slot}`)
}

// The backend reads game data from ./data. A worktree that was never hydrated gets a copy of the main
// checkout's data (minus saved builds / save.json, same filter as the E2E fixture) so agent-driven runs
// never write into the owner's real builds.
function dataDirFor(p) {
  if (existsSync(path.join(REPO, 'data'))) return undefined
  const target = path.join(p.scratch, 'data')
  if (existsSync(target)) return target
  const main = execFileSync('git', ['-C', REPO, 'worktree', 'list', '--porcelain'], { encoding: 'utf8' })
    .split('\n').find(l => l.startsWith('worktree '))?.slice(9).trim()
  const src = main && path.join(main, 'data')
  if (!src || !existsSync(src)) throw new Error('no data/ here or in the main checkout: run `npm run fetch:data` first')
  cpSync(src, target, {
    recursive: true,
    filter: s => {
      const rel = path.relative(src, s)
      return !rel || (rel.split(path.sep)[0] !== 'builds' && rel !== 'save.json') || rel === 'builds'
    },
  })
  return target
}

function run(cmd, args, env) {
  const child = spawn(cmd, args, { cwd: REPO, stdio: 'inherit', shell: process.platform === 'win32', env: { ...process.env, ...env } })
  // A child killed by a signal has code null: report failure, not success.
  child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
}

function main() {
  const mode = process.argv[2] || 'info'
  if (!MODES.includes(mode)) {
    console.error(`unknown mode "${mode}": use ${MODES.join(' | ')}`); process.exit(2)
  }
  if (mode === 'release') { release(); process.exit(0) }
  const p = portsFor(claimSlot())

  if (mode === 'info') {
    console.log(JSON.stringify(p, null, 2))
  } else if (mode === 'electron') {
    mkdirSync(p.userData, { recursive: true })
    const dataDir = dataDirFor(p)
    console.log(`[dev-slot ${p.slot}] backend :${p.backendPort}  vite :${p.vitePort}  CDP :${p.cdpPort}`)
    console.log(`[dev-slot ${p.slot}] drive it: agent-browser --session slot${p.slot}-electron connect ${p.cdpPort}`)
    run('npx', ['electron-vite', 'dev', '--remoteDebuggingPort', String(p.cdpPort)], {
      TLI_DEV_PYTHON_PORT: String(p.backendPort),
      TLI_DEV_USERDATA: p.userData,
      TLI_DEV_VITE_PORT: String(p.vitePort),
      ...(dataDir ? { TLI_DATA_DIR: dataDir } : {}),
    })
  } else if (mode === 'web') {
    if (!existsSync(path.join(REPO, 'dist-web', 'index.html'))) {
      console.error('dist-web/ is not built: run `npm run build:web` first'); process.exit(1)
    }
    console.log(`[dev-slot ${p.slot}] web :${p.webPort}`)
    console.log(`[dev-slot ${p.slot}] drive it: agent-browser --session slot${p.slot}-web open http://127.0.0.1:${p.webPort}/index.html`)
    run('node', [path.join('e2e', 'serve-dist-web.mjs')], { TLI_E2E_WEB_PORT: String(p.webPort) })
  } else if (mode === 'e2e') {
    // Same builds test:e2e runs first, so the slot never tests stale or missing out/ and dist-web/.
    // Pass --no-build to skip when you just built.
    const args = process.argv.slice(3)
    if (!args.includes('--no-build')) {
      for (const script of ['build', 'build:web']) {
        const r = spawnSync('npm', ['run', script], { cwd: REPO, stdio: 'inherit', shell: process.platform === 'win32' })
        if (r.status !== 0) process.exit(r.status ?? 1)
      }
    }
    run('npx', ['playwright', 'test', '-c', 'e2e', ...args.filter(a => a !== '--no-build')], {
      TLI_E2E_PYTHON_PORT: String(p.e2eBackendPort),
      TLI_E2E_WEB_PORT: String(p.e2eWebPort),
    })
  }
}

// Run only when invoked as a script, so tests can import portsFor/MAX_SLOTS without claiming a slot.
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main()
