import json
import os
import re
import time
import uuid

from persistence import folders_manager

_SAFE_ID = re.compile(r'^[A-Za-z0-9_-]+$')


def _dir() -> str:
    # Persisted user data lives under TLI_PERSIST_DIR when set (the web build points this at an IndexedDB-backed
    # dir so builds survive reloads); otherwise it falls back to the game-data dir, as desktop has always done.
    # Evaluated per-call (not at import) so it always reflects the env in effect when a request runs — the web
    # worker sets TLI_PERSIST_DIR after this module may already be imported.
    root = os.environ.get('TLI_PERSIST_DIR') or os.environ.get('TLI_DATA_DIR') or os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
    return os.path.normpath(os.path.join(root, 'builds'))


def _file(build_id: str) -> str:
    if not _SAFE_ID.fullmatch(build_id):
        raise ValueError(f"Invalid build id: {build_id!r}")
    return os.path.join(_dir(), f"{build_id}.txt")


def _parse_nodes(raw: str) -> dict[str, int]:
    nodes: dict[str, int] = {}
    if not raw:
        return nodes
    for entry in raw.split(','):
        entry = entry.strip()
        if ':' in entry:
            nid, pts = entry.rsplit(':', 1)
            try:
                nodes[nid.strip()] = int(pts)
            except ValueError:
                pass
    return nodes


def _read_file(build_id: str) -> dict:
    data: dict[str, str] = {}
    path = _file(build_id)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                data[k.strip()] = v.strip()

    slots = []
    for i in range(1, 5):
        tree = data.get(f'slot{i}_tree', '').strip()
        if tree:
            nodes = _parse_nodes(data.get(f'slot{i}_nodes', ''))
            core_raw = data.get(f'slot{i}_core_talents', '')
            core_selections = json.loads(core_raw) if core_raw else {}
            slots.append({'treeName': tree, 'nodeStates': nodes, 'coreTalentSelections': core_selections})
        else:
            slots.append(None)

    slates_raw = data.get('slates', '')
    slates = json.loads(slates_raw) if slates_raw else []

    slate_inventory_raw = data.get('slateInventory', '')
    slate_inventory = json.loads(slate_inventory_raw) if slate_inventory_raw else []

    prisms_raw = data.get('prisms', '')
    prisms = json.loads(prisms_raw) if prisms_raw else []
    prism_inventory_raw = data.get('prismInventory', '')
    prism_inventory = json.loads(prism_inventory_raw) if prism_inventory_raw else []

    conditions_raw = data.get('conditions', '')
    conditions = json.loads(conditions_raw) if conditions_raw else []

    gear_raw = data.get('gear', '')
    gear = json.loads(gear_raw) if gear_raw else []

    skills_raw = data.get('skills', '')
    skills = json.loads(skills_raw) if skills_raw else []

    character_level_raw = data.get('characterLevel', '')
    character_level = int(character_level_raw) if character_level_raw.isdigit() else 1
    has_prism = data.get('hasPrism', 'false').lower() == 'true'

    condition_values_raw = data.get('conditionValues', '')
    condition_values = json.loads(condition_values_raw) if condition_values_raw else {}

    trait_id = data.get('trait_id', '') or None
    trait_level_raw = data.get('trait_level', '1')
    trait_level = int(trait_level_raw) if trait_level_raw.isdigit() else 1
    slot_levels_raw = data.get('trait_slot_levels', '')
    trait_slot_levels = json.loads(slot_levels_raw) if slot_levels_raw else [trait_level, 1, 1, 1]
    advanced_raw = data.get('advanced_trait_selections', '')
    advanced_trait_selections = json.loads(advanced_raw) if advanced_raw else []
    trait_tree_allocations_raw = data.get('trait_tree_allocations', '')
    trait_tree_allocations = json.loads(trait_tree_allocations_raw) if trait_tree_allocations_raw else []

    tss_raw = data.get('trait_skill_supports', '')
    trait_skill_supports = json.loads(tss_raw) if tss_raw else []
    licorice_prepared_skill = data.get('licorice_prepared_skill', '') or None
    elixir_ingredients_raw = data.get('elixir_ingredients', '')
    elixir_ingredients = json.loads(elixir_ingredients_raw) if elixir_ingredients_raw else {}

    hero_memories_raw = data.get('hero_memories', '')
    hero_memories = json.loads(hero_memories_raw) if hero_memories_raw else [None, None, None]

    memory_inventory_raw = data.get('memoryInventory', '')
    memory_inventory = json.loads(memory_inventory_raw) if memory_inventory_raw else []

    pact_spirits_raw = data.get('pact_spirits', '')
    pact_spirits = json.loads(pact_spirits_raw) if pact_spirits_raw else [None, None, None]

    fates_raw = data.get('fates', '')
    fates = json.loads(fates_raw) if fates_raw else {}
    undetermined_raw = data.get('undetermined', '')
    undetermined = json.loads(undetermined_raw) if undetermined_raw else [None, None, None]

    notes_raw = data.get('notes', '')
    notes = json.loads(notes_raw) if notes_raw else ''

    condition_state_raw = data.get('conditionState', '')
    condition_state = json.loads(condition_state_raw) if condition_state_raw else {}

    custom_mods_raw = data.get('customMods', '')
    custom_mods = json.loads(custom_mods_raw) if custom_mods_raw else []

    loadouts_raw = data.get('loadouts', '')
    loadouts = json.loads(loadouts_raw) if loadouts_raw else []
    active_loadout_id = data.get('activeLoadoutId', '') or ''

    target_config_raw = data.get('targetConfig', '')
    target_config = json.loads(target_config_raw) if target_config_raw else None

    enemy_config_raw = data.get('enemyConfig', '')
    enemy_config = json.loads(enemy_config_raw) if enemy_config_raw else None

    # Timestamps (epoch seconds). Files predating this field have neither line — fall back to the
    # file's own mtime for both, so a legacy build still sorts/displays sensibly.
    created_at_raw = data.get('createdAt', '')
    updated_at_raw = data.get('updatedAt', '')
    try:
        created_at = float(created_at_raw) if created_at_raw else os.path.getmtime(path)
    except ValueError:
        created_at = os.path.getmtime(path)
    try:
        updated_at = float(updated_at_raw) if updated_at_raw else os.path.getmtime(path)
    except ValueError:
        updated_at = os.path.getmtime(path)

    return {
        'id': data.get('id', build_id),
        'createdAt': created_at,
        'updatedAt': updated_at,
        'name': data.get('name', ''),
        'slots': slots,
        'slates': slates,
        'slateInventory': slate_inventory,
        'prisms': prisms,
        'prismInventory': prism_inventory,
        'conditions': conditions,
        'conditionValues': condition_values,
        'conditionState': condition_state,
        'gear': gear,
        'skills': skills,
        'characterLevel': character_level,
        'hasPrism': has_prism,
        'traitId': trait_id,
        'traitLevel': trait_level,
        'traitSlotLevels': trait_slot_levels,
        'advancedTraitSelections': advanced_trait_selections,
        'traitTreeAllocations': trait_tree_allocations,
        'traitSkillSupports': trait_skill_supports,
        'licoricePreparedSkill': licorice_prepared_skill,
        'elixirIngredients': elixir_ingredients,
        'heroMemories': hero_memories,
        'memoryInventory': memory_inventory,
        'pactSpirits': pact_spirits,
        'fates': fates,
        'undetermined': undetermined,
        'notes': notes,
        'customMods': custom_mods,
        'loadouts': loadouts,
        'activeLoadoutId': active_loadout_id,
        'targetConfig': target_config,
        'enemyConfig': enemy_config,
    }


def _write_file(build: dict) -> None:
    os.makedirs(_dir(), exist_ok=True)
    slots = build.get('slots') or [None, None, None, None]
    slates = build.get('slates') or []
    with open(_file(build['id']), 'w') as f:
        f.write(f"id={build['id']}\n")
        f.write(f"name={build['name']}\n")
        f.write(f"createdAt={build.get('createdAt', time.time())}\n")
        f.write(f"updatedAt={build.get('updatedAt', time.time())}\n")
        for i, slot in enumerate(slots, 1):
            if slot:
                tree = slot.get('treeName', '')
                node_states = slot.get('nodeStates', {})
                nodes_str = ','.join(f"{k}:{v}" for k, v in node_states.items() if v > 0)
                core = slot.get('coreTalentSelections') or {}
            else:
                tree = ''
                nodes_str = ''
                core = {}
            f.write(f"slot{i}_tree={tree}\n")
            f.write(f"slot{i}_nodes={nodes_str}\n")
            f.write(f"slot{i}_core_talents={json.dumps(core, separators=(',', ':'))}\n")
        f.write(f"slates={json.dumps(slates, separators=(',', ':'))}\n")
        slate_inventory = build.get('slateInventory') or []
        f.write(f"slateInventory={json.dumps(slate_inventory, separators=(',', ':'))}\n")
        prisms = build.get('prisms') or []
        f.write(f"prisms={json.dumps(prisms, separators=(',', ':'))}\n")
        prism_inventory = build.get('prismInventory') or []
        f.write(f"prismInventory={json.dumps(prism_inventory, separators=(',', ':'))}\n")
        conditions = build.get('conditions') or []
        f.write(f"conditions={json.dumps(conditions, separators=(',', ':'))}\n")
        condition_values = build.get('conditionValues') or {}
        f.write(f"conditionValues={json.dumps(condition_values, separators=(',', ':'))}\n")
        gear = build.get('gear') or []
        f.write(f"gear={json.dumps(gear, separators=(',', ':'))}\n")
        skills = build.get('skills') or []
        f.write(f"skills={json.dumps(skills, separators=(',', ':'))}\n")
        f.write(f"characterLevel={build.get('characterLevel', 1)}\n")
        f.write(f"hasPrism={'true' if build.get('hasPrism') else 'false'}\n")
        f.write(f"trait_id={build.get('traitId', '') or ''}\n")
        slot_levels = build.get('traitSlotLevels') or [1, 1, 1, 1]
        f.write(f"trait_slot_levels={json.dumps(slot_levels, separators=(',', ':'))}\n")
        advanced = build.get('advancedTraitSelections') or []
        f.write(f"advanced_trait_selections={json.dumps(advanced, separators=(',', ':'))}\n")
        tree_allocations = build.get('traitTreeAllocations') or []
        f.write(f"trait_tree_allocations={json.dumps(tree_allocations, separators=(',', ':'))}\n")
        # Trait skill supports (Holy Domain), Licorice Note's prepared skill, and the scent-bottle Elixir
        # ingredients — persisted so they survive save/reload (were previously dropped).
        trait_skill_supports = build.get('traitSkillSupports') or []
        f.write(f"trait_skill_supports={json.dumps(trait_skill_supports, separators=(',', ':'))}\n")
        f.write(f"licorice_prepared_skill={build.get('licoricePreparedSkill') or ''}\n")
        elixir_ingredients = build.get('elixirIngredients') or {}
        f.write(f"elixir_ingredients={json.dumps(elixir_ingredients, separators=(',', ':'))}\n")
        hero_memories = build.get('heroMemories') or [None, None, None]
        f.write(f"hero_memories={json.dumps(hero_memories, separators=(',', ':'))}\n")
        memory_inventory = build.get('memoryInventory') or []
        f.write(f"memoryInventory={json.dumps(memory_inventory, separators=(',', ':'))}\n")
        pact_spirits = build.get('pactSpirits') or [None, None, None]
        f.write(f"pact_spirits={json.dumps(pact_spirits, separators=(',', ':'))}\n")
        fates = build.get('fates') or {}
        f.write(f"fates={json.dumps(fates, separators=(',', ':'))}\n")
        undetermined = build.get('undetermined') or [None, None, None]
        f.write(f"undetermined={json.dumps(undetermined, separators=(',', ':'))}\n")
        notes = build.get('notes') or ''
        f.write(f"notes={json.dumps(notes, separators=(',', ':'))}\n")
        condition_state = build.get('conditionState') or {}
        f.write(f"conditionState={json.dumps(condition_state, separators=(',', ':'))}\n")
        custom_mods = build.get('customMods') or []
        f.write(f"customMods={json.dumps(custom_mods, separators=(',', ':'))}\n")
        loadouts = build.get('loadouts') or []
        f.write(f"loadouts={json.dumps(loadouts, separators=(',', ':'))}\n")
        f.write(f"activeLoadoutId={build.get('activeLoadoutId', '') or ''}\n")
        target_config = build.get('targetConfig')
        if target_config:
            f.write(f"targetConfig={json.dumps(target_config, separators=(',', ':'))}\n")
        enemy_config = build.get('enemyConfig')
        if enemy_config:
            f.write(f"enemyConfig={json.dumps(enemy_config, separators=(',', ':'))}\n")


def load() -> list[dict]:
    d = _dir()
    if not os.path.isdir(d):
        return []
    builds = []
    for fname in sorted(os.listdir(d)):
        if fname.endswith('.txt'):
            try:
                builds.append(_read_file(fname[:-4]))
            except Exception:
                pass
    return builds


def save_build(build: dict) -> dict:
    if not build.get('id'):
        build['id'] = str(uuid.uuid4())[:8]

    # Timestamps are stamped server-side, never trusted from the client. updatedAt is always "now";
    # createdAt is preserved from the existing file on disk when there is one, else "now" (first save).
    now = time.time()
    created_at = now
    try:
        created_at = _read_file(build['id']).get('createdAt', now)
    except (OSError, ValueError):
        pass
    build['createdAt'] = created_at
    build['updatedAt'] = now

    _write_file(build)
    return build


def delete_build(build_id: str) -> bool:
    path = _file(build_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    folders_manager.remove_build(build_id)
    return True
