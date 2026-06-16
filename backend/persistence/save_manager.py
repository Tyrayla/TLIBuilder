import json
import os

def _save_path() -> str:
    # Persisted last-session save lives under TLI_PERSIST_DIR when set (the web build points this at an
    # IndexedDB-backed dir so restore-last-build survives reloads); otherwise it falls back to the game-data dir.
    # Evaluated per-call (not at import) so it reflects the env in effect when a request runs.
    root = os.environ.get('TLI_PERSIST_DIR') or os.environ.get('TLI_DATA_DIR') or os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
    return os.path.normpath(os.path.join(root, 'save.json'))


def save(tree_name: str, nodes: dict[str, int],
         core_talents: dict[str, str | None] | None = None) -> None:
    path = _save_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data: dict = {"tree": tree_name, "nodes": nodes}
    if core_talents is not None:
        data["core_talents"] = core_talents
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load() -> dict | None:
    path = _save_path()
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def clear() -> None:
    path = _save_path()
    if os.path.exists(path):
        os.remove(path)
