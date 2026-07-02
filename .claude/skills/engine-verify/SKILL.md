---
name: engine-verify
description: Run the TLI Builder engine verification suite after changing engine code — typecheck, Python tests, the consumable-universe scan, and the golden re-capture (with an additive-only diff check). Use when asked to "verify the engine", "run the checks/tests", "re-capture goldens", or at the end of the add-stat / add-condition / add-hero-trait / add-skill / add-support skills.
---

# engine-verify

Runs the full verification gate for engine changes. **Never commits** — report results and let Tyra decide.
See `docs/ENGINE_AUTHORING.md` for the gotchas this enforces.

## 1. Typecheck (only if frontend/TS changed)
From the repo root:
```
npx tsc --noEmit -p tsconfig.web.json 2>&1 | grep -cE "error TS"
```
Expect `0`. (Run from repo root — running elsewhere falsely reports `1` because the config isn't found.)

## 2. Python tests
```
cd backend && python -m pytest -q 2>&1 | tail -5
```
If a specific area changed, run its file first for a fast signal (e.g. `python -m pytest tests/test_channeled.py -q`).

## 3. Consumable-universe scan
Part of the full suite, but call it out — it's the easy-to-forget one:
```
cd backend && python -m pytest tests/test_consumable_universe.py -q 2>&1 | tail -5
```
If it fails listing a missing stat, add that stat to the `consumed |= {...}` block in
`backend/engine/consumable_universe.py` (only stats the engine reads on every run; see the doc).

## 4. Golden re-capture (only when output legitimately changed)
Golden tests fail when you intentionally change engine output (new `OffenseResult`/`HitFormResult` field, a new
always-read stat entering `consumed_stats`, a new `@_register`'d skill, or a real damage change).

**First, prove the diff is additive-only** (no pre-existing value changed — only new keys added). From `backend`:
```
python - <<'PY'
import json, os
from server import engine_stats, EngineStatsRequest
from tests.test_support_skill_goldens import _request, _canonical, _GOLDEN_DIR
def changed(old, new, path=""):
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k not in new: yield f"{path}.{k} REMOVED"
            else: yield from changed(old[k], new[k], f"{path}.{k}")
    elif isinstance(old, list) and isinstance(new, list):
        rem = [x for x in old if x not in new]
        if rem: yield f"{path}: REMOVED {rem}"
    elif old != new:
        yield f"{path}: {old!r} -> {new!r}"
for sid in ["chain_lightning","moon_strike","berserking_blade"]:
    g = json.load(open(os.path.join(_GOLDEN_DIR, f"{sid}.json"), encoding="utf-8"))
    c = json.loads(json.dumps(_canonical(engine_stats(EngineStatsRequest(**_request(sid)))), sort_keys=True))
    diffs = list(changed(g, c))
    print(sid, "value changes:", diffs if diffs else "NONE (additive only)")
PY
```
- If any spot-checked skill shows a real value change, **stop** — that's a behavior change to review with Tyra,
  not a mechanical re-capture.
- If additive-only, re-capture: delete the changed fixtures and run twice (first captures + skips, second asserts):
```
cd backend
rm -f tests/fixtures/support_skill_golden/*.json tests/fixtures/scope_golden/*.json
python -m pytest tests/test_support_skill_goldens.py tests/test_skill_scope_nochange.py -q 2>&1 | tail -3
python -m pytest tests/test_support_skill_goldens.py tests/test_skill_scope_nochange.py -q 2>&1 | tail -3
```
(Only delete the goldens you expect to change. A new skill adds a brand-new `support_skill_golden/<id>.json`.)

## 5. Verification-entry drift check (KB ↔ engine)
Every shipped mechanic should have a Verification Database entry (`data/verification/<id>.json`) — even an empty
`unverified` one — so the KB never falls behind the engine. This step **warns** (does not fail) on registered
skills / bespoke modules lacking an entry. From `backend`:
```
py -3.12 - <<'PY'
import os, re, glob, json
def norm(s): return s.lower().replace("_","-").replace(" ","-")
entries = [json.load(open(p,encoding="utf-8")) for p in glob.glob(os.path.join("..","data","verification","*.json"))]
# Coverage = every entry id + every skill name listed on an entry (so groundshaker→demolisher's
# skills:["Groundshaker"], icebound_beam→channeled's skills:["Icebound Beam"], etc. all count).
cover = set()
for e in entries:
    cover.add(norm(e.get("id","")))
    for s in e.get("skills", []): cover.add(norm(s))
def covered(i):
    n = norm(i); return any(n == c or n in c or c in n for c in cover)
ids = set(re.findall(r'@_register\("([^"]+)"\)', open("engine/skill_resolver.py",encoding="utf-8").read()))
missing = sorted(i for i in ids if not covered(i))
print("registered skills w/o a verification entry:", missing if missing else "none")
# Bespoke subsystem modules (fuzzy — eyeball against entries if you added a new subsystem).
mods = [os.path.splitext(f)[0] for d in ("engine/hero_traits","engine/skill_effects")
        for f in os.listdir(d) if f.endswith(".py") and not f.startswith("_")]
print("bespoke modules (cross-check manually):", sorted(mods))
PY
```
Report anything under "w/o a verification entry" to Tyra and offer to run `/add-verification`. The check
normalizes `_`↔`-` and cross-references entry `skills`, so a fuzzy name (e.g. `groundshaker` → the `demolisher`
entry via its `skills:["Groundshaker"]`) already counts as covered — don't force a 1:1 id match.

## 6. Report
Summarize: tsc error count, pytest pass count, consumable-universe status, whether goldens were re-captured
(and that the diff was additive-only), and any verification-entry drift. Do **not** commit. Surface anything
unexpected to Tyra.
