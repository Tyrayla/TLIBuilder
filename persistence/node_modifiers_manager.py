import json
import os
import re

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "node_modifiers.json")
)


def _sort_key(node_id: str) -> tuple[int, int]:
    m = re.search(r"_c(\d+)_r(\d+)$", node_id)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def load() -> dict:
    if not os.path.exists(_PATH):
        return {}
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_node(tree_name: str, node_id: str, modifiers: list[dict]) -> None:
    """modifiers = [{"text": str, "values": [float, ...]}, ...]"""
    data = load()
    tree_data: dict = data.get(tree_name, {})

    if modifiers:
        tree_data[node_id] = modifiers
    else:
        tree_data.pop(node_id, None)

    sorted_ids = sorted(tree_data.keys(), key=_sort_key)
    data[tree_name] = {nid: tree_data[nid] for nid in sorted_ids}

    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
