import json
import os

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_SAVE_PATH = os.path.normpath(os.path.join(_DATA_ROOT, 'save.json'))


def save(tree_name: str, nodes: dict[str, int],
         core_talents: dict[str, str | None] | None = None) -> None:
    os.makedirs(os.path.dirname(_SAVE_PATH), exist_ok=True)
    data: dict = {"tree": tree_name, "nodes": nodes}
    if core_talents is not None:
        data["core_talents"] = core_talents
    with open(_SAVE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load() -> dict | None:
    if not os.path.exists(_SAVE_PATH):
        return None
    with open(_SAVE_PATH) as f:
        return json.load(f)


def clear() -> None:
    if os.path.exists(_SAVE_PATH):
        os.remove(_SAVE_PATH)
