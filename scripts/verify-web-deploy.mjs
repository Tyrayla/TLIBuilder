// Confirm a Cloudflare Pages deploy actually reached the live URL before calling `deploy:web[:data]`
// done. `wrangler pages deploy` returns as soon as the deployment is created, but the custom
// domain (tlibuilder.com / tlibuilder-data CDN) can lag the *.pages.dev deployment by up to
// ~a minute of edge-cache propagation — this polls until the live content matches the local
// build output, or gives up after --timeout seconds.
//
// Usage:
//   node scripts/verify-web-deploy.mjs [--url=https://tlibuilder.com] [--dist=dist-web]
//                                       [--check=index.html|manifest.json]
//                                       [--timeout=90] [--interval=5]
//
// --check=index.html   (default, for the app deploy) — extracts the hashed entry-script path
//                       from <dist>/index.html and polls --url until the live HTML references
//                       the same path.
// --check=manifest.json (for the data CDN deploy) — byte-compares manifest.json, engine-data.zip and
//                       each file under <dist>/<season>/ against --url. The manifest carries a
//                       `content` fingerprint of the season catalogs and icons (export_web_data.py
//                       content_digest), so it also covers the ~1000 icons without fetching them.
//                       A deploy that silently went to a preview branch instead of production, or
//                       never landed, fails this check.

import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { createHash } from 'node:crypto'

const FETCH_TIMEOUT_MS = 15_000

function parseArgs(argv) {
  const out = { url: 'https://tlibuilder.com', dist: 'dist-web', check: 'index.html', timeout: 90, interval: 5 }
  for (const arg of argv) {
    const m = /^--([^=]+)=(.*)$/.exec(arg)
    if (!m) continue
    const [, key, val] = m
    if (key === 'timeout' || key === 'interval') {
      const n = Number(val)
      if (!Number.isFinite(n) || n <= 0) throw new Error(`--${key} must be a positive number, got "${val}"`)
      out[key] = n
    } else {
      out[key] = val
    }
  }
  if (out.check !== 'index.html' && out.check !== 'manifest.json') {
    throw new Error(`--check must be "index.html" or "manifest.json", got "${out.check}"`)
  }
  return out
}

function extractEntryScriptPath(html) {
  const m = /<script[^>]+type="module"[^>]+src="([^"]+)"/.exec(html)
  if (!m) throw new Error('Could not find a <script type="module" src="..."> tag in the local index.html')
  return m[1]
}

function extractStaticDataBase(bundle) {
  const match = /https:\/\/tlibuilder-data\.pages\.dev/.exec(bundle)
  if (!match) {
    throw new Error('The local web entry bundle does not contain the static data CDN URL. Check VITE_STATIC_DATA_BASE.')
  }
  return match[0]
}

async function verifyStaticCatalog(entryPath, args) {
  const localBundlePath = join(process.cwd(), args.dist, entryPath.replace(/^\//, ''))
  if (!existsSync(localBundlePath)) throw new Error(`${localBundlePath} not found — could not inspect the built entry bundle`)
  const dataBase = extractStaticDataBase(readFileSync(localBundlePath, 'utf-8'))
  const manifestUrl = `${dataBase}/manifest.json`
  const manifestResponse = await fetch(manifestUrl, { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })
  if (!manifestResponse.ok) throw new Error(`HTTP ${manifestResponse.status} fetching static data manifest ${manifestUrl}`)
  const manifest = await manifestResponse.json()
  if (!manifest?.season || typeof manifest.season !== 'string') throw new Error(`Static data manifest at ${manifestUrl} has no season`)
  const catalogUrl = `${dataBase}/${manifest.season}/hero_traits.json`
  const catalogResponse = await fetch(catalogUrl, { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })
  if (!catalogResponse.ok) throw new Error(`HTTP ${catalogResponse.status} fetching static catalog ${catalogUrl}`)
  const catalog = await catalogResponse.json()
  if (!Array.isArray(catalog?.traits) || !catalog.traits.length) throw new Error(`Static catalog at ${catalogUrl} contains no hero traits`)
  console.log(`verify-web-deploy: static catalog ready (${manifest.season}, ${catalog.traits.length} hero traits)`)
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollUntil(label, checkOnce, { timeout, interval }) {
  const start = Date.now()
  const deadline = start + timeout * 1000
  let attempt = 0
  for (;;) {
    attempt += 1
    const elapsed = ((Date.now() - start) / 1000).toFixed(0)
    try {
      const ok = await checkOnce()
      if (ok) {
        console.log(`verify-web-deploy: ${label} matched live after ${elapsed}s (attempt ${attempt})`)
        return true
      }
    } catch (err) {
      console.log(`verify-web-deploy: attempt ${attempt} (${elapsed}s) — ${err.message}`)
    }
    if (Date.now() >= deadline) return false
    await sleep(interval * 1000)
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const distPath = join(process.cwd(), args.dist)

  if (args.check === 'manifest.json') {
    const localPath = join(distPath, 'manifest.json')
    if (!existsSync(localPath)) throw new Error(`${localPath} not found — did the build step run first?`)
    const local = JSON.parse(readFileSync(localPath, 'utf-8'))
    if (!local?.season || typeof local.season !== 'string') throw new Error(`${localPath} has no season`)
    const seasonDir = join(distPath, local.season)
    if (!existsSync(seasonDir)) throw new Error(`${seasonDir} not found — did the build step run first?`)
    if (typeof local.content !== 'string') throw new Error(`${localPath} has no content fingerprint — re-run npm run build:web:data`)
    if (!existsSync(join(distPath, 'engine-data.zip'))) throw new Error(`${join(distPath, 'engine-data.zip')} not found — did the build step run first?`)
    const files = [
      'manifest.json',
      'engine-data.zip',
      ...readdirSync(seasonDir).filter((f) => statSync(join(seasonDir, f)).isFile()).map((f) => `${local.season}/${f}`),
    ]
    const sha = (buf) => createHash('sha256').update(buf).digest('hex')
    const expected = new Map(files.map((f) => [f, sha(readFileSync(join(distPath, f)))]))
    const base = args.url.replace(/\/$/, '')
    console.log(`verify-web-deploy: polling ${base} until ${files.length} data files match the local build ...`)
    const ok = await pollUntil(
      `${files.length} data files`,
      async () => {
        // In parallel, so one attempt costs about one fetch timeout rather than files.length of them.
        const results = await Promise.all(files.map(async (f) => {
          const res = await fetch(`${base}/${f}`, { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })
          if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${base}/${f}`)
          return sha(Buffer.from(await res.arrayBuffer())) === expected.get(f) ? null : f
        }))
        const stale = results.filter(Boolean)
        if (stale.length) throw new Error(`${stale.length} file(s) differ from the local build: ${stale.join(', ')}`)
        return true
      },
      args
    )
    if (!ok) {
      console.error(`verify-web-deploy: FAILED — ${base} did not serve the local data build within ${args.timeout}s.`)
      console.error('This can be propagation lag (retry the check), a deploy that went to a preview branch instead of')
      console.error('production, or a deploy that silently failed — check `wrangler pages deployment list`.')
      process.exit(1)
    }
    return
  }

  const localPath = join(distPath, 'index.html')
  if (!existsSync(localPath)) throw new Error(`${localPath} not found — did the build step run first?`)
  const entryPath = extractEntryScriptPath(readFileSync(localPath, 'utf-8'))
  console.log(`verify-web-deploy: polling ${args.url} for entry script ${entryPath} ...`)
  const ok = await pollUntil(
    'entry script',
    async () => {
      const res = await fetch(args.url, { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })
      if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${args.url}`)
      const html = await res.text()
      return html.includes(entryPath)
    },
    args
  )
  if (!ok) {
    console.error(`verify-web-deploy: FAILED — ${args.url} did not serve ${entryPath} within ${args.timeout}s.`)
    console.error('This can be genuine propagation lag (retry the check) or a deploy that silently failed — check `wrangler pages deployment list`.')
    process.exit(1)
  }
  await verifyStaticCatalog(entryPath, args)
}

main().catch((err) => {
  console.error(`verify-web-deploy: ${err.message}`)
  process.exit(1)
})
