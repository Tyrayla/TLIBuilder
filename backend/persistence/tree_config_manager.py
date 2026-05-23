import json
import os
import re

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_DIR = os.path.normpath(os.path.join(_DATA_ROOT, 'trees'))


def _slug(tree_name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', tree_name.lower()).strip('_')


def _path(tree_name: str) -> str:
    return os.path.join(_DIR, f"{_slug(tree_name)}.json")


def _tree_to_config(tree) -> dict:
    return {
        "nodes": [
            {
                "id": n.id,
                "column": n.column,
                "row": n.row,
                "node_type": n.node_type.value,
                "max_points": n.max_points,
            }
            for n in tree.nodes.values()
        ],
        "connections": [
            {"from": id1, "to": id2}
            for id1, id2 in tree.connections
        ],
    }


def _save(tree_name: str, config: dict) -> None:
    os.makedirs(_DIR, exist_ok=True)
    with open(_path(tree_name), 'w') as f:
        json.dump(config, f, indent=2)


def load(tree_name: str) -> dict | None:
    path = _path(tree_name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def snapshot(tree_name: str, tree) -> dict:
    """Serialize the Python tree to JSON on first edit; return existing config if already present."""
    config = load(tree_name)
    if config is not None:
        return config
    config = _tree_to_config(tree)
    _save(tree_name, config)
    return config


def upsert_node(tree_name: str, tree, node_data: dict) -> dict:
    config = snapshot(tree_name, tree)
    existing = next((n for n in config["nodes"] if n["id"] == node_data["id"]), None)
    if existing:
        existing.update(node_data)
    else:
        config["nodes"].append(node_data)
    _save(tree_name, config)
    return config


def remove_node(tree_name: str, tree, node_id: str) -> dict:
    config = snapshot(tree_name, tree)
    config["nodes"] = [n for n in config["nodes"] if n["id"] != node_id]
    config["connections"] = [
        c for c in config["connections"]
        if c["from"] != node_id and c["to"] != node_id
    ]
    _save(tree_name, config)
    return config


def toggle_connection(tree_name: str, tree, src: str, dst: str) -> dict:
    config = snapshot(tree_name, tree)
    exists = any(c["from"] == src and c["to"] == dst for c in config["connections"])
    if exists:
        config["connections"] = [
            c for c in config["connections"]
            if not (c["from"] == src and c["to"] == dst)
        ]
    else:
        config["connections"].append({"from": src, "to": dst})
    _save(tree_name, config)
    return config
