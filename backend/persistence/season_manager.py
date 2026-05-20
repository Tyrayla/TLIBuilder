import json
import os
import shutil

_SEASONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons")
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


def save_legendary_gear(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "_legendary_gear.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_legendary_gear(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_legendary_gear.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_new_god_talents(season: str, talents: list[dict]) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "_new_god_talents.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(talents, f, indent=2)


def load_new_god_talents(season: str) -> list[dict] | None:
    path = os.path.join(_season_dir(season), "_new_god_talents.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_season_summary(name: str) -> dict:
    d = _season_dir(name)
    trees: list[str] = []
    node_counts: dict[str, int] = {}
    new_god_count: int | None = None
    legendary_gear_count: int | None = None
    if os.path.isdir(d):
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".json"):
                continue
            if fname.startswith("_"):
                fpath = os.path.join(d, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        fdata = json.load(f)
                    if fname == "_new_god_talents.json":
                        new_god_count = len(fdata)
                    elif fname == "_legendary_gear.json":
                        legendary_gear_count = len(fdata.get("items", []))
                except Exception:
                    pass
                continue
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
    return {
        "name": name, "trees": trees, "node_counts": node_counts,
        "new_god_count": new_god_count, "legendary_gear_count": legendary_gear_count,
    }
