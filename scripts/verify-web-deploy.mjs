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
// --check=manifest.json (for the data CDN deploy) — compares <dist>/manifest.json against
//                       --url/manifest.json as parsed JSON (so trailing whitespace/formatting
//                       differences don't cause a false failure).

import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

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
    const remoteUrl = `${args.url.replace(/\/$/, '')}/manifest.json`
    console.log(`verify-web-deploy: polling ${remoteUrl} for manifest.json ${JSON.stringify(local)} ...`)
    const ok = await pollUntil(
      'manifest.json',
      async () => {
        const res = await fetch(remoteUrl, { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${remoteUrl}`)
        const remote = JSON.parse(await res.text())
        return JSON.stringify(remote) === JSON.stringify(local)
      },
      args
    )
    if (!ok) {
      console.error(`verify-web-deploy: FAILED — ${remoteUrl} did not match local manifest within ${args.timeout}s.`)
      console.error('This can be genuine propagation lag (retry the check) or a deploy that silently failed — check `wrangler pages deployment list`.')
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
}

main().catch((err) => {
  console.error(`verify-web-deploy: ${err.message}`)
  process.exit(1)
})
