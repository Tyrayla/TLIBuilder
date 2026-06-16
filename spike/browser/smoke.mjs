// Headless smoke test for the web build: serves dist-web (app + data, same origin) and loads it in Chromium,
// then waits for the Pyodide compute worker to reach `ready` (which includes a warm engine_stats), capturing
// console errors / failed requests / CSP violations. Run: node smoke.mjs
import { chromium } from 'playwright'
import http from 'http'
import { readFile } from 'fs/promises'
import { existsSync, statSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'dist-web')
const PORT = 8800
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.zip': 'application/zip', '.wasm': 'application/wasm', '.png': 'image/png', '.svg': 'image/svg+xml' }

const server = http.createServer(async (req, res) => {
  let p = decodeURIComponent((req.url || '/').split('?')[0])
  if (p === '/') p = '/index.html'
  const fp = path.join(ROOT, p)
  if (!existsSync(fp) || !statSync(fp).isFile()) { res.writeHead(404); res.end('not found'); return }
  try {
    const buf = await readFile(fp)
    res.writeHead(200, { 'content-type': MIME[path.extname(fp)] || 'application/octet-stream', 'access-control-allow-origin': '*' })
    res.end(buf)
  } catch (e) { res.writeHead(500); res.end(String(e)) }
})

await new Promise(r => server.listen(PORT, '127.0.0.1', r))
console.log(`serving ${ROOT} at http://127.0.0.1:${PORT}`)

const browser = await chromium.launch()
const page = await browser.newPage()
const errors = [], failed = [], consoleErrs = []
page.on('pageerror', e => errors.push(String(e)))
page.on('requestfailed', r => failed.push(`${r.url().slice(0, 90)} -> ${r.failure()?.errorText}`))
page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 200)) })

let ok = false
try {
  await page.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForFunction(() => (document.getElementById('root')?.children.length || 0) > 0, { timeout: 30000 })
  console.log('app rendered (#root populated)')
  const t0 = Date.now()
  await page.waitForFunction(
    () => window.__tliComputeReady === true || !!window.__tliComputeError,
    { timeout: 180000 },
  )
  const st = await page.evaluate(() => ({ ready: window.__tliComputeReady === true, err: window.__tliComputeError || null }))
  console.log(`compute worker: ${st.ready ? 'READY' : 'ERROR'} in ${((Date.now() - t0) / 1000).toFixed(1)}s${st.err ? ' — ' + st.err : ''}`)
  ok = st.ready && !st.err
  if (ok) {
    // Verify a specific tree loads through the worker (the path-decode fix).
    const tree = await page.evaluate(() => window.__tliWebApi('GET', '/api/tree/God of War').catch(e => ({ error: String(e) })))
    const treeOk = tree && Array.isArray(tree.nodes) && tree.nodes.length > 0
    console.log(`tree "God of War": ${treeOk ? `OK (${tree.nodes.length} nodes)` : 'FAIL ' + JSON.stringify(tree).slice(0, 120)}`)
    ok = ok && treeOk
  }
  if (ok) {
    // Persistence: save a build, reload the page (fresh worker), confirm it survived the IDBFS round-trip.
    const saved = await page.evaluate(() => window.__tliWebApi('POST', '/api/builds',
      { name: 'SMOKE_PERSIST', slots: [null, null, null, null] }).catch(e => ({ error: String(e) })))
    const savedId = saved && saved.id
    console.log(`save build: ${savedId ? `OK (id ${savedId})` : 'FAIL ' + JSON.stringify(saved).slice(0, 120)}`)
    if (savedId) {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForFunction(() => window.__tliComputeReady === true || !!window.__tliComputeError, { timeout: 180000 })
      const after = await page.evaluate((id) => window.__tliWebApi('GET', '/api/builds')
        .then(list => ({ has: Array.isArray(list) && list.some(b => b.id === id), n: Array.isArray(list) ? list.length : -1 }))
        .catch(e => ({ error: String(e) })), savedId)
      const persisted = !!(after && after.has)
      console.log(`persist across reload: ${persisted ? `OK (${after.n} build(s) after reload)` : 'FAIL ' + JSON.stringify(after).slice(0, 120)}`)
      ok = ok && persisted
      await page.evaluate((id) => window.__tliWebApi('DELETE', '/api/builds/' + id).catch(() => {}), savedId)
    } else { ok = false }
  }
} catch (e) {
  console.log('TIMEOUT/ERROR waiting for app/worker:', String(e).split('\n')[0])
}

console.log(`\n=== console errors (${consoleErrs.length}) ===`); consoleErrs.slice(0, 12).forEach(e => console.log('  ', e))
console.log(`=== page errors (${errors.length}) ===`); errors.slice(0, 8).forEach(e => console.log('  ', e))
console.log(`=== failed requests (${failed.length}) ===`); failed.slice(0, 12).forEach(e => console.log('  ', e))
console.log(`\nSMOKE: ${ok ? 'PASS — worker ready, engine computed in the browser' : 'FAIL — see above'}`)

await browser.close(); server.close()
process.exit(ok ? 0 : 1)
