// Fetch the private game dataset into ./data.
//
// The dataset is NOT tracked in this repo (see .gitignore). It lives in the private
// `tli-data` repository and is pulled in at build time. Run `npm run fetch:data` after
// cloning. CI provides TLI_DATA_TOKEN (a read-only token for tli-data) as a secret.
//
// Env:
//   TLI_DATA_TOKEN  read token for the private repo (falls back to GH_TOKEN, or your
//                   local git credentials if neither is set).
//   TLI_DATA_REF    branch or TAG to fetch (default: main). Pin per-season with a tag.
//                   A raw commit SHA is not supported (git clone --branch takes a ref).
//   TLI_DATA_REPO   override the repo host/path (default: github.com/Tyrayla/tli-data.git).
//
// Security: the token is passed to git via config in the ENVIRONMENT (GIT_CONFIG_*), never
// in the clone URL or argv, so a git error can't echo it and it isn't visible in the
// process table. (Same mechanism actions/checkout uses.)
//
// User builds under data/builds/ are preserved. Everything else under data/ is pruned and
// replaced, so a catalog removed upstream between seasons doesn't linger stale.

import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync, cpSync, existsSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const REPO = process.env.TLI_DATA_REPO || 'github.com/Tyrayla/tli-data.git'
const REF = process.env.TLI_DATA_REF || 'main'
const TOKEN = process.env.TLI_DATA_TOKEN || process.env.GH_TOKEN || ''
const dest = join(process.cwd(), 'data')

const env = { ...process.env }
if (TOKEN) {
  const basic = Buffer.from(`x-access-token:${TOKEN}`).toString('base64')
  env.GIT_CONFIG_COUNT = '1'
  env.GIT_CONFIG_KEY_0 = 'http.extraHeader'
  env.GIT_CONFIG_VALUE_0 = `Authorization: Basic ${basic}`
}

const tmp = mkdtempSync(join(tmpdir(), 'tli-data-'))
try {
  console.log(`Fetching game data from https://${REPO} @ ${REF} ...`)
  execFileSync('git', ['clone', '--depth', '1', '--branch', REF, `https://${REPO}`, tmp], {
    stdio: 'inherit',
    env,
  })
  const src = join(tmp, 'data')
  if (!existsSync(src)) {
    throw new Error(`tli-data@${REF} has no data/ directory — nothing to copy.`)
  }
  // Preserve local user builds; prune-and-replace everything else so stale files don't linger.
  if (existsSync(dest)) {
    for (const entry of readdirSync(dest)) {
      if (entry === 'builds') continue
      rmSync(join(dest, entry), { recursive: true, force: true })
    }
  }
  cpSync(src, dest, { recursive: true, force: true })
  console.log(`Game data written to ${dest}`)
} catch (err) {
  console.error('\nfetch:data failed.')
  if (!TOKEN) {
    console.error('No TLI_DATA_TOKEN/GH_TOKEN set — relying on local git credentials for a PRIVATE repo.')
    console.error('If you have access, ensure `git clone https://github.com/Tyrayla/tli-data` works; otherwise set TLI_DATA_TOKEN.')
  }
  console.error(String(err && err.message ? err.message : err))
  process.exit(1)
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
