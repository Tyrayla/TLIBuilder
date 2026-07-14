from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Literal

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_CONDITIONS_PATH = os.path.join(_DATA_ROOT, 'conditions.json')


@dataclass(frozen=True)
class ConditionDef:
    key: str
    label: str
    category: str
    value_type: Literal["boolean", "numeric", "enum"] = "boolean"
    enum_values: tuple[str, ...] = ()     # for value_type == "enum": the selectable options (a dropdown)
    default_enum: str = ""                 # default selected option for an enum condition
    numeric_min: float = 0
    numeric_max: float | None = None
    min_base: float = 0
    min_from_stat: str | None = None
    max_base: float = 0
    max_from_stat: str | None = None
    unit: str = ""
    default_value: float = 0
    default_bool: bool = False
    visible: bool = True
    source: str = "user"
    trait_id: str | None = None   # set on hero-trait conditions; UI shows them only for the selected trait


def _load() -> tuple[list[ConditionDef], dict[str, str], dict[str, list[str]]]:
    try:
        with open(_CONDITIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], {}, {}
    conds = [ConditionDef(**({**c, "enum_values": tuple(c["enum_values"])} if "enum_values" in c else c))
             for c in data.get("conditions", [])]
    derived = data.get("derived_keys", {})
    # Derived NUMERICS: each key is the SUM of its listed source condition values (e.g. any_blessings =
    # focus + agility + tenacity). Re-derived each fixed-point iteration in compute._clamp_and_rederive.
    derived_numeric = data.get("derived_numeric_keys", {})
    return conds, derived, derived_numeric


def _condition_defaults(conds: list[ConditionDef]) -> tuple[dict[str, bool], dict[str, float]]:
    bool_defaults = {c.key: c.default_bool for c in conds if c.value_type == "boolean"}
    numeric_defaults = {c.key: c.default_value for c in conds if c.value_type == "numeric"}
    return bool_defaults, numeric_defaults


ALL_CONDITIONS: list[ConditionDef]
DERIVED_ACTIVE_KEYS: dict[str, str]
DERIVED_NUMERIC_KEYS: dict[str, list[str]]
ALL_CONDITIONS, DERIVED_ACTIVE_KEYS, DERIVED_NUMERIC_KEYS = _load()

CONDITIONS_BY_KEY: dict[str, ConditionDef] = {c.key: c for c in ALL_CONDITIONS}

# Cached (bool_defaults, numeric_defaults) — condition_defaults() is called 2-10x per recompute (once per
# fixed-point iteration, from compute._derive_views and aggregator.aggregate's own fallback), and rebuilding
# two ~130-entry dicts from ALL_CONDITIONS every call is pure waste since the catalog only changes via
# reload(). Callers only ever read/copy the returned dicts (never mutate them), so sharing these cached
# objects across calls is safe.
_CONDITION_DEFAULTS: tuple[dict[str, bool], dict[str, float]] = _condition_defaults(ALL_CONDITIONS)


def reload() -> None:
    """Reload condition definitions from disk. Called by dev endpoints after writes."""
    global ALL_CONDITIONS, DERIVED_ACTIVE_KEYS, DERIVED_NUMERIC_KEYS, CONDITIONS_BY_KEY, _CONDITION_DEFAULTS
    ALL_CONDITIONS, DERIVED_ACTIVE_KEYS, DERIVED_NUMERIC_KEYS = _load()
    CONDITIONS_BY_KEY = {c.key: c for c in ALL_CONDITIONS}
    _CONDITION_DEFAULTS = _condition_defaults(ALL_CONDITIONS)


def condition_defaults() -> tuple[dict[str, bool], dict[str, float]]:
    """Catalog defaults split into the same two shapes the engine's `active_booleans`/`numeric_vals`
    evaluation views use: {key: default_bool} for boolean conditions, {key: default_value} for numeric
    ones. Callers pre-seed their views with these, then overlay the build's actual `condition_state` so an
    ABSENT key evaluates at its catalog default (matching what the client shows/seeds) instead of silently
    reading as 0.0/False. Enum conditions (e.g. groundshaker_area_selector) are read directly by their own
    consumers via `condition_state.get(key, default_enum)` — not through active_booleans/numeric_vals — so
    they're intentionally excluded here.

    Cached at module scope (rebuilt by `reload()`) since callers invoke this 2-10x per fixed-point
    recompute; the returned dicts are shared, not copies — never mutate them in place."""
    return _CONDITION_DEFAULTS
