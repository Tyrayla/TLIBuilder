import json
import os
import shutil

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_SEASONS_DIR = os.path.normpath(os.path.join(_DATA_ROOT, 'seasons'))
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


def load_all_season_trees(season: str) -> dict[str, dict]:
    """Return {slug: tree_data} for all tree files in the season (excludes _ prefixed files)."""
    d = _season_dir(season)
    result: dict[str, dict] = {}
    if not os.path.isdir(d):
        return result
    for fname in os.listdir(d):
        if fname.endswith(".json") and not fname.startswith("_"):
            slug = fname[:-5]
            tree_data = load_season_tree(season, slug)
            if tree_data:
                result[slug] = tree_data
    return result


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


_legendary_gear_cache: dict[str, dict] = {}


def save_legendary_gear(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "_legendary_gear.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    _legendary_gear_cache[season] = data
    # Also save lightweight index (name/id/level/base_type only)
    index_items = [
        {
            "item_id": item["item_id"],
            "name": item["name"],
            "required_level": item.get("required_level") or 0,
            "base_type": item.get("base_type") or "",
        }
        for item in data.get("items", [])
    ]
    index_path = os.path.join(d, "_legendary_gear_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"season": season, "items": index_items}, f, indent=2)


def load_legendary_gear(season: str) -> dict | None:
    if season in _legendary_gear_cache:
        return _legendary_gear_cache[season]
    path = os.path.join(_season_dir(season), "_legendary_gear.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _legendary_gear_cache[season] = data
    return data


def load_legendary_gear_index(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_legendary_gear_index.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_skills(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "_skills.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_skills(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_skills.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_skills(season: str) -> None:
    path = os.path.join(_season_dir(season), "_skills.json")
    if os.path.exists(path):
        os.remove(path)


def save_hero_traits(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "_hero_traits.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_hero_traits(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_hero_traits.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_hero_traits(season: str) -> None:
    path = os.path.join(_season_dir(season), "_hero_traits.json")
    if os.path.exists(path):
        os.remove(path)


def save_pact_spirits(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_pact_spirits.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_pact_spirits(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_pact_spirits.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_pact_spirits(season: str) -> None:
    path = os.path.join(_season_dir(season), "_pact_spirits.json")
    if os.path.exists(path):
        os.remove(path)


def save_craft_base_types(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_craft_base_types.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_craft_base_types(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_craft_base_types.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_craft_base_types(season: str) -> None:
    path = os.path.join(_season_dir(season), "_craft_base_types.json")
    if os.path.exists(path):
        os.remove(path)
    path2 = os.path.join(_season_dir(season), "_craft_base_items.json")
    if os.path.exists(path2):
        os.remove(path2)


def save_craft_base_items(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_craft_base_items.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_craft_base_items(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_craft_base_items.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_grafts(season: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_grafts.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_grafts(season: str) -> dict | None:
    path = os.path.join(_season_dir(season), "_grafts.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_grafts(season: str) -> None:
    path = os.path.join(_season_dir(season), "_grafts.json")
    if os.path.exists(path):
        os.remove(path)


def _save_singleton(season: str, filename: str, data: dict) -> None:
    d = _season_dir(season)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load_singleton(season: str, filename: str) -> dict | None:
    path = os.path.join(_season_dir(season), filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _delete_singleton(season: str, filename: str) -> None:
    path = os.path.join(_season_dir(season), filename)
    if os.path.exists(path):
        os.remove(path)


def save_destiny(season: str, data: dict) -> None:
    _save_singleton(season, "_destiny.json", data)


def load_destiny(season: str) -> dict | None:
    return _load_singleton(season, "_destiny.json")


def delete_destiny(season: str) -> None:
    _delete_singleton(season, "_destiny.json")


def save_ethereal_prism(season: str, data: dict) -> None:
    _save_singleton(season, "_ethereal_prism.json", data)


def load_ethereal_prism(season: str) -> dict | None:
    return _load_singleton(season, "_ethereal_prism.json")


def delete_ethereal_prism(season: str) -> None:
    _delete_singleton(season, "_ethereal_prism.json")


def save_hero_memories(season: str, data: dict) -> None:
    _save_singleton(season, "_hero_memories.json", data)


def load_hero_memories(season: str) -> dict | None:
    return _load_singleton(season, "_hero_memories.json")


def delete_hero_memories(season: str) -> None:
    _delete_singleton(season, "_hero_memories.json")


def save_memory_revival(season: str, data: dict) -> None:
    _save_singleton(season, "_memory_revival.json", data)


def load_memory_revival(season: str) -> dict | None:
    return _load_singleton(season, "_memory_revival.json")


def delete_memory_revival(season: str) -> None:
    _delete_singleton(season, "_memory_revival.json")


def save_tower_sequence(season: str, data: dict) -> None:
    _save_singleton(season, "_tower_sequence.json", data)


def load_tower_sequence(season: str) -> dict | None:
    return _load_singleton(season, "_tower_sequence.json")


def delete_tower_sequence(season: str) -> None:
    _delete_singleton(season, "_tower_sequence.json")


def save_divinity_slates(season: str, data: dict) -> None:
    _save_singleton(season, "_divinity_slates.json", data)


def load_divinity_slates(season: str) -> dict | None:
    return _load_singleton(season, "_divinity_slates.json")


def delete_divinity_slates(season: str) -> None:
    _delete_singleton(season, "_divinity_slates.json")


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
    skill_count: int | None = None
    hero_trait_count: int | None = None
    pact_spirit_count: int | None = None
    craft_base_type_count: int | None = None
    graft_count: int | None = None
    destiny_count: int | None = None
    ethereal_prism_count: int | None = None
    hero_memories_count: int | None = None
    memory_revival_count: int | None = None
    tower_sequence_count: int | None = None
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
                    elif fname == "_skills.json":
                        skill_count = len(fdata.get("skills", []))
                    elif fname == "_hero_traits.json":
                        hero_trait_count = len(fdata.get("traits", []))
                    elif fname == "_pact_spirits.json":
                        pact_spirit_count = len(fdata.get("spirits", []))
                    elif fname == "_craft_base_types.json":
                        craft_base_type_count = len(fdata.get("base_types", []))
                    elif fname == "_grafts.json":
                        graft_count = len(fdata.get("grafts", []))
                    elif fname == "_destiny.json":
                        destiny_count = fdata.get("item_count", len(fdata.get("items", [])))
                    elif fname == "_ethereal_prism.json":
                        ethereal_prism_count = fdata.get("modifier_count", len(fdata.get("modifiers", [])))
                    elif fname == "_hero_memories.json":
                        hero_memories_count = fdata.get("affix_count", len(fdata.get("affixes", [])))
                    elif fname == "_memory_revival.json":
                        memory_revival_count = fdata.get("affix_count", len(fdata.get("affixes", [])))
                    elif fname == "_tower_sequence.json":
                        tower_sequence_count = fdata.get("entry_count", len(fdata.get("entries", [])))
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
        "skill_count": skill_count, "hero_trait_count": hero_trait_count,
        "pact_spirit_count": pact_spirit_count, "craft_base_type_count": craft_base_type_count,
        "graft_count": graft_count,
        "destiny_count": destiny_count, "ethereal_prism_count": ethereal_prism_count,
        "hero_memories_count": hero_memories_count, "memory_revival_count": memory_revival_count,
        "tower_sequence_count": tower_sequence_count,
    }
