// Build the web app with its data served from the same origin, for the web e2e target.
//
// The shipped web build reads catalogs + engine-data.zip from the live data CDN
// (tlibuilder-data.pages.dev). For tests that means a commit's engine runs against whatever data is in
// production, and the run depends on the CDN being up. This builds the data bundle from the local data/
// (run `npm run fetch:data` first), builds the app pointed at the same-origin path /data, and copies the
// bundle into dist-web/data — so e2e/serve-dist-web.mjs serves app and data together and the browser
// never touches the CDN. Pyodide itself still loads from jsDelivr.
//
// Usage:  node scripts/build-web-local-data.mjs     (then: npx playwright test -c e2e --project=web)
// Never deploy the dist-web this produces: its data base is /data, not the CDN.

import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, rmSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = process.cwd()
const DATA_BASE = '/data'

function run(script, env = {}) {
  console.log(`> npm run ${script}`)
  // One command string: npm is npm.cmd on Windows, which needs a shell, and Node deprecates shell + args.
  const r = spawnSync(`npm run ${script}`, { stdio: 'inherit', shell: true, env: { ...process.env, ...env } })
  if (r.status !== 0) process.exit(r.status ?? 1)
}

if (!existsSync(join(ROOT, 'data', 'conditions.json'))) {
  console.error('data/ is not hydrated — run `npm run fetch:data` first.')
  process.exit(1)
}

run('build:web:data')
// Vite gives an existing process env var priority over .env.web, so this overrides the CDN base.
run('build:web', { VITE_STATIC_DATA_BASE: DATA_BASE })

// build:web empties dist-web, so copy the data bundle in afterwards.
const dest = join(ROOT, 'dist-web', 'data')
rmSync(dest, { recursive: true, force: true })
cpSync(join(ROOT, 'web-data'), dest, { recursive: true })
// Fail here, not as a Pyodide boot timeout minutes into the test run.
for (const f of ['manifest.json', 'engine-data.zip']) {
  if (!existsSync(join(dest, f))) {
    console.error(`dist-web${DATA_BASE}/${f} is missing after the copy — check build:web:data's output in web-data/.`)
    process.exit(1)
  }
}
console.log(`web-data copied to dist-web${DATA_BASE}; the app reads its data from ${DATA_BASE}.`)
