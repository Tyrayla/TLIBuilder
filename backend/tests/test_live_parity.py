"""Live-backend parity: compare the RUNNING dev backend against the in-process (source) engine for the same
payloads. Its job is to catch the "stale backend" class of disconnect — where the app is talking to a Python
process started before the latest code change, so the UI shows results the source no longer produces — WITHOUT
needing manual in-app testing.

Behaviour:
  • No backend listening on 8765-8774  → every case is skipped (so normal/CI `pytest` is unaffected).
  • A backend IS running                → each payload is computed BOTH live (HTTP) and in-process (import), and
                                          their key offense outputs must match. A mismatch means the running
                                          backend is STALE (or otherwise diverged) → relaunch the dev app.

Run it after relaunching, or any time the app is open, to verify the live client matches HEAD.
"""
import json
import urllib.request

import pytest

from tests.mock_build import make_request
from server import engine_stats, EngineStatsRequest


def _find_port() -> int | None:
    for p in range(8765, 8775):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{p}/api/trees", timeout=1).read()
            return p
        except Exception:
            continue
    return None


_PORT = _find_port()
# Representative payloads — extend as new mechanics land (each should exercise a Config input → engine path).
_CASES = [
    ("chromatic_default", make_request("chromatic_shot", 20)),
    ("chromatic_shots_1", make_request("chromatic_shot", 20, extra_conditions={"chromatic_shots_on_target": 1})),
    ("chain_lightning", make_request("chain_lightning", 14)),
]


def _live(payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}/api/engine/stats",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _source(payload: dict) -> dict:
    r = engine_stats(EngineStatsRequest(**payload))
    return r if isinstance(r, dict) else r.model_dump()


# The offense fields whose divergence would signal a real stale-backend disconnect.
_KEYS = ("total_dps", "total_dps_vs_target", "skills_per_second")


@pytest.mark.skipif(_PORT is None, reason="no live dev backend on 8765-8774 (start the app to run live parity)")
@pytest.mark.parametrize("name,payload", _CASES, ids=[c[0] for c in _CASES])
def test_live_matches_source(name, payload):
    live, src = _live(payload), _source(payload)
    lo, so = live.get("offense") or {}, src.get("offense") or {}
    diffs = [f"{k}: live={lo.get(k)!r} source={so.get(k)!r}"
             for k in _KEYS if not _approx(lo.get(k), so.get(k))]
    # auto_conditions parity too (this is exactly the field whose staleness caused the Projectile Hits disconnect)
    if (live.get("auto_conditions") or {}) != (src.get("auto_conditions") or {}):
        diffs.append(f"auto_conditions: live={live.get('auto_conditions')} source={src.get('auto_conditions')}")
    assert not diffs, (
        f"LIVE backend differs from source for '{name}' — the running dev backend is likely STALE; relaunch "
        f"the app.\n  " + "\n  ".join(diffs))


def _approx(a, b, tol=1e-6) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b
