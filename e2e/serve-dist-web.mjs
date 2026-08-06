// Static server for dist-web (app + data bundles, same origin) — promoted from spike/browser/smoke.mjs.
// Started by playwright.config.ts webServer; can also run standalone: node e2e/serve-dist-web.mjs
import http from 'http'
import { readFile } from 'fs/promises'
import { existsSync, statSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist-web')
const PORT = Number(process.env.TLI_E2E_WEB_PORT || 8800)
// 127.0.0.1 by default; set TLI_E2E_WEB_HOST=0.0.0.0 to preview from a phone on the LAN.
const HOST = process.env.TLI_E2E_WEB_HOST || '127.0.0.1'
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.zip': 'application/zip', '.wasm': 'application/wasm', '.png': 'image/png', '.svg': 'image/svg+xml' }

const server = http.createServer(async (req, res) => {
  let p = decodeURIComponent((req.url || '/').split('?')[0])
  if (p === '/') p = '/index.html'
  const fp = path.join(ROOT, p)
  // Containment must be boundary-aware: a bare startsWith(ROOT) would also serve a sibling dist-web-* dir.
  const inRoot = fp === ROOT || fp.startsWith(ROOT + path.sep)
  if (!inRoot || !existsSync(fp) || !statSync(fp).isFile()) { res.writeHead(404); res.end('not found'); return }
  try {
    const buf = await readFile(fp)
    res.writeHead(200, { 'content-type': MIME[path.extname(fp)] || 'application/octet-stream' })
    res.end(buf)
  } catch (e) { res.writeHead(500); res.end(String(e)) }
})

server.listen(PORT, HOST, () => console.log(`serving ${ROOT} at http://${HOST}:${PORT}`))
