/// <reference lib="webworker" />
// Pyodide compute worker (web build only). Loads Pyodide + the backend Python + the engine-data bundle, then
// runs the real `engine_stats` off the main thread so the UI never blocks. Protocol:
//   main -> worker: { type:'init', backendUrl, dataBase, season } | { type:'compute', id, reqJson }
//   worker -> main: { type:'progress', msg } | { type:'ready' } | { type:'result', id, respJson }
//                 | { type:'error', id?, msg }
// Deps: pydantic/fastapi are installed via micropip at init for now (network, one-time). A pre-deploy step will
// vendor these wheels so it's fully offline — see the web plan.

const PYODIDE_VERSION = '0.27.7'
const PYODIDE_INDEX = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

interface InitMsg { type: 'init'; backendUrl: string; dataBase: string; season: string }
interface ComputeMsg { type: 'compute'; id: number; reqJson: string }
type InMsg = InitMsg | ComputeMsg

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let py: any = null
let computeFn: ((reqJson: string) => string) | null = null
let initPromise: Promise<void> | null = null

const post = (m: unknown) => (self as unknown as Worker).postMessage(m)
const progress = (msg: string) => post({ type: 'progress', msg })

async function fetchBytes(url: string): Promise<Uint8Array> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetch ${url} -> ${res.status}`)
  return new Uint8Array(await res.arrayBuffer())
}

async function init(msg: InitMsg): Promise<void> {
  progress('Loading engine runtime…')
  // Load Pyodide from the CDN (kept external so Vite doesn't try to bundle it).
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE_INDEX}pyodide.mjs`)
  py = await loadPyodide({ indexURL: PYODIDE_INDEX })

  progress('Loading Python packages…')
  await py.loadPackage('micropip')
  await py.runPythonAsync(`import micropip\nawait micropip.install(['fastapi', 'python-multipart'])`)

  progress('Loading game data…')
  const [backendZip, dataZip] = await Promise.all([
    fetchBytes(msg.backendUrl),
    fetchBytes(`${msg.dataBase}/engine-data.zip`),
  ])
  py.FS.mkdir('/be'); py.unpackArchive(backendZip, 'zip', { extractDir: '/be' })
  py.FS.mkdir('/data'); py.unpackArchive(dataZip, 'zip', { extractDir: '/data' })
  py.FS.mkdir('/stubs'); py.FS.writeFile('/stubs/uvicorn.py', 'def run(*a, **k):\n    pass\n')

  progress('Starting engine…')
  await py.runPythonAsync(`
import os, sys
sys.path.insert(0, '/stubs'); sys.path.insert(0, '/be')
os.environ['TLI_DATA_DIR'] = '/data'; os.environ['TLI_DEV_MODE'] = '0'
import json
from fastapi.encoders import jsonable_encoder
import server
server.season_manager.set_active_season(${JSON.stringify(msg.season)})

def _compute(req_json):
    req = server.EngineStatsRequest(**json.loads(req_json))
    return json.dumps(jsonable_encoder(server.engine_stats(req)))
`)
  computeFn = py.globals.get('_compute')
  // Warm once so the first real recompute is fast (skills cache + consumable_universe build).
  try { computeFn!('{"slots":[null,null,null,null],"skills":[],"character":[],"condition_state":{"level":90}}') } catch { /* warm best-effort */ }
  post({ type: 'ready' })
}

self.onmessage = async (e: MessageEvent<InMsg>) => {
  const msg = e.data
  if (msg.type === 'init') {
    initPromise = init(msg)
    try { await initPromise } catch (err) { post({ type: 'error', msg: `init failed: ${String(err)}` }) }
    return
  }
  if (msg.type === 'compute') {
    try {
      if (initPromise) await initPromise
      if (!computeFn) throw new Error('worker not initialized')
      post({ type: 'result', id: msg.id, respJson: computeFn(msg.reqJson) })
    } catch (err) {
      post({ type: 'error', id: msg.id, msg: String(err) })
    }
  }
}
