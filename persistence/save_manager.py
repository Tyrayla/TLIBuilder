import json
import os

_SAVE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "save.json")
_SAVE_PATH = os.path.normpath(_SAVE_PATH)


def save(tree_name: str, nodes: dict[str, int]) -> None:
    os.makedirs(os.path.dirname(_SAVE_PATH), exist_ok=True)
    with open(_SAVE_PATH, "w") as f:
        json.dump({"tree": tree_name, "nodes": nodes}, f, indent=2)


def load() -> dict | None:
    if not os.path.exists(_SAVE_PATH):
        return None
    with open(_SAVE_PATH) as f:
        return json.load(f)


def clear() -> None:
    if os.path.exists(_SAVE_PATH):
        os.remove(_SAVE_PATH)
