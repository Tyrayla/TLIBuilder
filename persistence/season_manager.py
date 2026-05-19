import json
import os
import shutil

_SEASONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "seasons")
)
_ACTIVE_FILE = os.path.join(_SEASONS_DIR, ".active")


def _ensure_dir():
    os.makedirs(_SEASONS_DIR, exist_ok=True)


def list_seasons() -> list[str]:
    _ensure_dir()
    return sorted(
        d for d in os.listdir(_SEASONS_DIR)
        if os.path.isdir(os.path.join(_SEASONS_DIR, d)) and not d.startswith(".")
    )


def get_active_season() -> str | None:
    if not os.path.exists(_ACTIVE_FILE):
        return None
    with open(_ACTIVE_FILE, encoding="utf-8") as f:
        name = f.read().strip()
    return name if name else None


def set_active_season(name: str | None) -> None:
    _ensure_dir()
    with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(name or "")


def _season_dir(season: str) -> str:
    return os.path.join(_SEASONS_DIR, season)


def load_season_tree(season: str, tree_slug: str) -> dict | None:
    path = os.path.join(_season_dir(season), f"{tree_slug}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_season_tree(season: str, tree_name: str, tree_slug: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{tree_slug}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def delete_season(name: str) -> None:
    d = _season_dir(name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    active = get_active_season()
    if active == name:
        set_active_season(None)


def get_season_summary(name: str) -> dict:
    d = _season_dir(name)
    trees: list[str] = []
    node_counts: dict[str, int] = {}
    if os.path.isdir(d):
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                slug = fname[:-5]
                try:
                    path = os.path.join(d, fname)
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    display = data.get("tree_name", slug)
                    trees.append(display)
                    node_counts[display] = len(data.get("nodes", []))
                except Exception:
                    pass
    return {"name": name, "trees": trees, "node_counts": node_counts}
