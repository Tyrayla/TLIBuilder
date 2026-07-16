"""Season identity index: affix_identity(text) → minted pooling_uuid, from the stored catalogs.

The aggregator stamps `SourceEntry.pooling_uuid = index.get(affix_identity(text))` on definition-level
contributions (gear / character / spirit / memory / trait / custom) at emit time; offense pools by
`pooling_uuid or affix_identity(text)`. Because the stamp is a pure function of the identity and the
mint is injective over identities (uuid5 over the canonical template), the induced partition is
byte-identical to affix_identity's — proven by tests/test_pooling_partition.py's index-equivalence
gate. Legacy builds and crafted-roll texts join through the same lookup with zero build-code changes.

NEVER consult this index for minted-suffix entries (supports `|item_id|role`, nodes/slates
`|tag|node_id`, core talents `|core|<name>`): their per-instance distinctness is deliberate (they
MULTIPLY); a definition-level uuid would collapse them into ADD. Suffixed texts can't hit the index
(it holds only catalog lines), but the aggregator doesn't even try — see the stamping rule there.

The index is cached per season and self-invalidates on a season-dir fingerprint (file count + max
mtime), so both in-process DevTools imports and the out-of-process reimport script are picked up
without explicit cache plumbing.
"""
from __future__ import annotations

import json
import os

from engine.affix_identity import affix_identity

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))

# A stored line's identity-bearing text, by record shape — first present wins: effect_raw (belt
# blends; effect_text is a derived wording), raw_text (parse_affix_text output), text (slim lines),
# modifier (hero-memory rows). Shared with tests/test_identity_crosscheck.py.
TEXT_KEYS = ("effect_raw", "raw_text", "text", "modifier")


def iter_identity_lines(obj, path: str = ""):
    """Yield (path, text, pooling_uuid) for every dict carrying a non-null pooling_uuid plus a
    known text key — schema-agnostic, so new identity-carrying surfaces are covered automatically."""
    if isinstance(obj, dict):
        pu = obj.get("pooling_uuid")
        if pu:
            for k in TEXT_KEYS:
                if isinstance(obj.get(k), str):
                    yield path, obj[k], pu
                    break
        for key, val in obj.items():
            yield from iter_identity_lines(val, f"{path}/{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from iter_identity_lines(val, f"{path}[{i}]")


def build_identity_index(season: str) -> dict[str, str]:
    """Walk every stored season file and map affix_identity(text) → pooling_uuid. Same-identity
    lines always carry the same uuid by construction (enforced by test_identity_crosscheck), so
    collisions cannot disagree; keep-first regardless."""
    season_dir = os.path.join(_DATA_ROOT, "seasons", season)
    index: dict[str, str] = {}
    if not os.path.isdir(season_dir):
        return index
    for fname in sorted(os.listdir(season_dir)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(season_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for _path, text, pu in iter_identity_lines(data):
            index.setdefault(affix_identity(text), pu)
    return index


# ── Cached access ─────────────────────────────────────────────────────────────

_cache: dict[str, tuple[tuple[int, float], dict[str, str]]] = {}


def _fingerprint(season: str) -> tuple[int, float]:
    season_dir = os.path.join(_DATA_ROOT, "seasons", season)
    count, latest = 0, 0.0
    try:
        with os.scandir(season_dir) as it:
            for e in it:
                if e.name.endswith(".json"):
                    count += 1
                    latest = max(latest, e.stat().st_mtime)
    except OSError:
        pass
    return count, latest


def get_identity_index(season: str) -> dict[str, str]:
    fp = _fingerprint(season)
    cached = _cache.get(season)
    if cached and cached[0] == fp:
        return cached[1]
    index = build_identity_index(season)
    _cache[season] = (fp, index)
    return index
