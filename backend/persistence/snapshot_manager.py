import json
import os

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_PATH = os.path.normpath(os.path.join(_DATA_ROOT, 'talent_snapshot.json'))


def exists() -> bool:
    return os.path.exists(_PATH)


def load() -> dict | None:
    if not os.path.exists(_PATH):
        return None
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(snapshot: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
