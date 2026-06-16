// Pyodide spike — measure whether the pure-Python TLI engine runs (and how fast) in WASM.
// Runs in Node via the `pyodide` npm package (NODEFS-mounts the real backend/ + data/), which is a
// representative proxy for the in-browser Web Worker the real web build would use.
//
// Usage:  node run.mjs
import { loadPyodide } from 'pyodide'
import { fileURLToPath } from 'url'
import { readFileSync } from 'fs'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(__dirname, '..', '..')
const BACKEND = path.join(REPO, 'backend').replace(/\\/g, '/')
const DATA = path.join(REPO, 'data').replace(/\\/g, '/')

const ms = (a, b) => `${(b - a).toFixed(0)} ms`
const heapMB = (py) => (py._module.HEAPU8.length / 1048576).toFixed(0)

async function main() {
  console.log('REPO:', REPO)
  const tLoad0 = performance.now()
  const py = await loadPyodide()
  const tLoad1 = performance.now()
  console.log(`pyodide runtime loaded: ${ms(tLoad0, tLoad1)}`)

  // Backend code: mount the real dir (in the browser worker this is a zip too; not the part under test here).
  py.FS.mkdir('/be'); py.FS.mount(py.FS.filesystems.NODEFS, { root: BACKEND }, '/be')
  // DATA: load the way the browser worker will — fetch engine-data.zip + unpackArchive into the FS (NO real-dir
  // mount). This verifies both the worker's data mechanism AND that the bundle is complete.
  const tUnz0 = performance.now()
  py.FS.mkdir('/data')
  const zipBytes = new Uint8Array(readFileSync(path.join(REPO, 'web-data', 'engine-data.zip')))
  py.unpackArchive(zipBytes, 'zip', { extractDir: '/data' })
  console.log(`engine-data.zip unpacked into FS: ${ms(tUnz0, performance.now())}`)
  // Stub uvicorn so `import server` doesn't pull the (unneeded) server runtime.
  py.FS.mkdir('/stubs'); py.FS.writeFile('/stubs/uvicorn.py', 'def run(*a, **k):\n    pass\n')

  const tDep0 = performance.now()
  // Try OFFLINE first: load from Pyodide's bundled package set (no PyPI). Falls back to micropip if missing.
  try {
    await py.loadPackage(['pydantic', 'fastapi'])
    console.log('deps via loadPackage (OFFLINE)')
  } catch (e) {
    console.log('loadPackage failed, falling back to micropip (network):', String(e).slice(0, 120))
    await py.loadPackage('micropip')
    await py.runPythonAsync(`import micropip\nawait micropip.install(['fastapi', 'python-multipart'])`)
  }
  const tDep1 = performance.now()
  console.log(`deps ready: ${ms(tDep0, tDep1)}`)

  const tImp0 = performance.now()
  await py.runPythonAsync(`
import os, sys
sys.path.insert(0, '/stubs')
sys.path.insert(0, '/be')
os.environ['TLI_DATA_DIR'] = '/data'
os.environ['TLI_DEV_MODE'] = '0'
# Phase 2a is in: the compute-path file reads now specify encoding='utf-8' and the one cp1252 data file was
# converted to utf-8, so the engine loads in WASM with NO encoding workaround.
import server
# The worker sets the active season explicitly (it knows it from the CDN manifest) rather than relying on a
# pointer file in the bundle — multi-season-safe.
server.season_manager.set_active_season('SS12')
print('server imported; active season =', server.season_manager.get_active_season())
`)
  const tImp1 = performance.now()
  console.log(`import server (load engine + data wiring): ${ms(tImp0, tImp1)}`)

  // Build a representative request (port of tests/mock_build.make_request) and time engine_stats.
  await py.runPythonAsync(`
import time, json
def _wc(slot, name, stat, val):
    return {"stat": stat, "display_value": val, "unit": "", "slot": slot, "item_name": name, "text": f"{name}:{stat}"}
def weapon(slot, name, dmin, dmax, aps, csr):
    return {"item_name": name, "contributions": [
        _wc(slot,name,"physical_dmg_gear_flat_min",dmin), _wc(slot,name,"physical_dmg_gear_flat_max",dmax),
        _wc(slot,name,"weapon_attack_speed",aps), _wc(slot,name,"weapon_crit_rating_flat",csr)]}
DUAL = [weapon("weapon1","Test Sword",200,350,1.3,600), weapon("weapon2","Test Axe",300,500,1.1,600)]
def char_contribs(level=90):
    g=max(level-1,0)
    return [{"stat":"max_life_flat","amount":50+13*g,"label":"Base","text":""},
            {"stat":"max_mana_flat","amount":40+5*g,"label":"Base","text":""},
            {"stat":"max_energy_flat","amount":4,"label":"Base","text":""},
            {"stat":"max_energy_flat","amount":level,"label":"Levels","text":""}]

def make_req(slots):
    return dict(slots=slots, gear=DUAL, character=char_contribs(90),
                condition_state={"level":90,"dual_wielding":True,"unique_weapon_types":2},
                skills=[{"slot":1,"skill_id":"chain_lightning","level":20}],
                main_skill={"skill_id":"chain_lightning","level":20}, attached_supports=[])

def run_once(req_dict):
    return server.engine_stats(server.EngineStatsRequest(**req_dict))

global LIGHT_REQ, HEAVY_REQ
LIGHT_REQ = make_req([None,None,None,None])

# HEAVY build ≈ a full build: ~25 talents in each of 4 trees (100) + slates + a full gear set with affix
# texts + pact-spirit + hero-memory effects + custom mods + a 4-support main skill — i.e. every text the
# engine has to parse/resolve per recompute.
def tree_slot(slug, n=25):
    d = json.load(open(f'/data/seasons/SS12/{slug}.json'))
    nodes = d['nodes'][:n]
    return {"treeName": d["tree_name"], "nodeStates": {nd["id"]: nd.get("max_rank", 1) for nd in nodes}}

def slate_from(slug, idxs):
    d = json.load(open(f'/data/seasons/SS12/{slug}.json'))
    ids = [d['nodes'][i]['id'] for i in idxs]
    return {"kind": "base", "cells": [[0,0]], "orientationIndex": 0, "shapeIndex": 0, "anchor": [0,0],
            "slots": [{"selectedNodeId": nid, "selectedCoreKey": None, "effects": [], "isCore": False} for nid in ids]}

GEAR_AFFIX_TEXTS = ["+10 % increased damage","+15 % Critical Strike Rating","+200 Maximum Life",
                    "+12 % Attack Speed","+25 % Cold damage","+18 % Critical Strike Damage"]
def armor(slot, name):
    return {"item_name": name, "unresolved_texts": GEAR_AFFIX_TEXTS,
            "contributions": [_wc(slot,name,"max_life_flat",250), _wc(slot,name,"armor_gear_flat",400)]}

SPIRIT_EFFECTS = [{"text": t, "source": "Spirit"} for t in
    ["+8 % increased damage","+12 % Critical Strike Damage","+5 % Attack Speed","+150 Maximum Life",
     "+10 % Lightning damage","+6 % Critical Strike Rating","+20 % Elemental Damage","+100 Maximum Mana",
     "+7 % increased damage","+9 % Cold damage","+4 % Attack Speed","+15 % Critical Strike Damage"]]
MEMORY_EFFECTS = [{"text": t, "source": "Memory"} for t in
    ["+200 Maximum Life","+15 % increased damage","+10 % Critical Strike Rating",
     "+8 % Attack Speed","+12 % Lightning damage","+150 Maximum Mana"]]
CUSTOM_MODS = ["+10 % increased damage","+5 % Attack Speed","+200 Maximum Life"]

HEAVY_SLOTS = [tree_slot(s) for s in ['warrior','ranger','magister','the_brave']]
HEAVY_SLATES = [slate_from('warrior',[0,1]), slate_from('ranger',[0,1]), slate_from('magister',[0,1])]
HEAVY_GEAR = DUAL + [armor("body","Body"), armor("helmet","Helm"), armor("gloves","Gloves"),
                     armor("boots","Boots"), armor("ring1","Ring")]
HEAVY_SUPPORTS = [{"slot":1,"item_id":sid,"skill_type":"support_skill","level":20,"enabled":True}
                  for sid in ['added_lightning_damage','overload','jump','electric_overload']]
HEAVY_REQ = make_req(HEAVY_SLOTS)
HEAVY_REQ.update(gear=HEAVY_GEAR, slates=HEAVY_SLATES, spirit_effects=SPIRIT_EFFECTS,
                 memory_effects=MEMORY_EFFECTS, custom_mods=CUSTOM_MODS, attached_supports=HEAVY_SUPPORTS,
                 skills=[{"slot":1,"skill_id":"chain_lightning","level":20,"supports":HEAVY_SUPPORTS}])

# warm both (first call also lazy-loads the skills cache)
_r = run_once(LIGHT_REQ); run_once(HEAVY_REQ)
_off = _r['offense'] if isinstance(_r, dict) else getattr(_r, 'offense', None)
_dps = (_off or {}).get('total_dps_vs_target') if isinstance(_off, dict) else getattr(_off, 'total_dps_vs_target', None)
print('compute OK — light offense.total_dps_vs_target =', _dps)
print('heavy: nodes=%d slates=%d gear=%d spirits=%d memories=%d' % (
    sum(len(s["nodeStates"]) for s in HEAVY_SLOTS), sum(len(s["slots"]) for s in HEAVY_SLATES),
    len(HEAVY_GEAR), len(SPIRIT_EFFECTS), len(MEMORY_EFFECTS)))
`)

  // Warm timing: median of N for each build
  const N = 10
  const measure = async (call) => {
    const t = []
    for (let i = 0; i < N; i++) { const t0 = performance.now(); await py.runPythonAsync(call); t.push(performance.now() - t0) }
    t.sort((a, b) => a - b)
    return { min: t[0], median: t[Math.floor(N / 2)], max: t[N - 1] }
  }
  const light = await measure(`run_once(LIGHT_REQ)`)
  const heavy = await measure(`run_once(HEAVY_REQ)`)
  const f = (x) => x.toFixed(0)
  console.log(`\n=== per-recompute (warm, ${N} runs) ===`)
  console.log(`LIGHT (empty trees):  min ${f(light.min)} · median ${f(light.median)} · max ${f(light.max)} ms`)
  console.log(`HEAVY (full build):   min ${f(heavy.min)} · median ${f(heavy.median)} · max ${f(heavy.max)} ms`)
  console.log(`WASM heap: ${heapMB(py)} MB`)
  console.log(`\nNote: Node-Pyodide is a representative proxy for the in-browser Web Worker; the one-time`)
  console.log(`runtime download (~6-10 MB) + ~1-3 s init happen once per session in a real browser.`)
}

main().catch(e => { console.error('SPIKE FAILED:', e); process.exit(1) })
