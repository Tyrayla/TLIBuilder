/// <reference lib="webworker" />
// Pyodide backend worker (web build only). Loads Pyodide + the backend Python + the engine-data bundle, then
// serves the FastAPI app as a general in-browser backend: it dispatches ANY (method, path, body) through the
// real ASGI app, so every endpoint (engine/stats, trees, resolve-mod, build-code, slate-pool, …) works exactly
// like the server — off the main thread so the UI never blocks. Protocol:
//   main -> worker: { type:'init', backendUrl, dataBase, season } | { type:'request', id, method, path, bodyJson }
//   worker -> main: { type:'progress', msg } | { type:'ready' }
//                 | { type:'result', id, status, body } | { type:'error', id?, msg }
// Deps: pydantic/fastapi via micropip at init (network, one-time). A pre-deploy step will vendor these wheels.

const PYODIDE_VERSION = '0.27.7'
const PYODIDE_INDEX = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

interface InitMsg { type: 'init'; backendUrl: string; dataBase: string; season: string }
interface RequestMsg { type: 'request'; id: number; method: string; path: string; bodyJson: string }
type InMsg = InitMsg | RequestMsg

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let py: any = null
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let apiFn: any = null   // async Python _api(method, path, body_text) -> '{"status":int,"body":str}'
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
import server
# Pyodide has no threads, but FastAPI runs sync (def) endpoints via run_in_threadpool — patch it to run inline.
import fastapi.routing, starlette.concurrency
async def _inline_threadpool(func, *a, **k):
    return func(*a, **k)
starlette.concurrency.run_in_threadpool = _inline_threadpool
fastapi.routing.run_in_threadpool = _inline_threadpool
server.season_manager.set_active_season(${JSON.stringify(msg.season)})

async def _api(method, path, body_text=''):
    p, _, qs = path.partition('?')
    scope = {'type':'http','http_version':'1.1','method':method,'path':p,'raw_path':p.encode(),
             'query_string':qs.encode(),'headers':[(b'content-type',b'application/json')],
             'scheme':'http','server':('localhost',80),'client':('127.0.0.1',0),'root_path':'',
             'asgi':{'version':'3.0','spec_version':'2.3'}}
    body = (body_text or '').encode()
    async def receive(): return {'type':'http.request','body':body,'more_body':False}
    state = {'status':500,'chunks':[]}
    async def send(m):
        if m['type']=='http.response.start': state['status']=m['status']
        elif m['type']=='http.response.body': state['chunks'].append(bytes(m.get('body',b'')))
    await server.app(scope, receive, send)
    return json.dumps({'status':state['status'],'body':b''.join(state['chunks']).decode('utf-8')})
`)
  apiFn = py.globals.get('_api')
  // Warm once so the first real recompute is fast (skills cache + consumable_universe build).
  try {
    await apiFn('POST', '/api/engine/stats', '{"slots":[null,null,null,null],"skills":[],"character":[],"condition_state":{"level":90}}')
  } catch { /* warm best-effort */ }
  post({ type: 'ready' })
}

self.onmessage = async (e: MessageEvent<InMsg>) => {
  const msg = e.data
  if (msg.type === 'init') {
    initPromise = init(msg)
    try { await initPromise } catch (err) { post({ type: 'error', msg: `init failed: ${String(err)}` }) }
    return
  }
  if (msg.type === 'request') {
    try {
      if (initPromise) await initPromise
      if (!apiFn) throw new Error('worker not initialized')
      const resStr = await apiFn(msg.method, msg.path, msg.bodyJson)
      const { status, body } = JSON.parse(resStr)
      post({ type: 'result', id: msg.id, status, body })
    } catch (err) {
      post({ type: 'error', id: msg.id, msg: String(err) })
    }
  }
}
