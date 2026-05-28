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
    value_type: Literal["boolean", "numeric"] = "boolean"
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


def _load() -> tuple[list[ConditionDef], dict[str, str]]:
    try:
        with open(_CONDITIONS_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], {}
    conds = [ConditionDef(**c) for c in data.get("conditions", [])]
    derived = data.get("derived_keys", {})
    return conds, derived


ALL_CONDITIONS: list[ConditionDef]
DERIVED_ACTIVE_KEYS: dict[str, str]
ALL_CONDITIONS, DERIVED_ACTIVE_KEYS = _load()

CONDITIONS_BY_KEY: dict[str, ConditionDef] = {c.key: c for c in ALL_CONDITIONS}


def reload() -> None:
    """Reload condition definitions from disk. Called by dev endpoints after writes."""
    global ALL_CONDITIONS, DERIVED_ACTIVE_KEYS, CONDITIONS_BY_KEY
    ALL_CONDITIONS, DERIVED_ACTIVE_KEYS = _load()
    CONDITIONS_BY_KEY = {c.key: c for c in ALL_CONDITIONS}
