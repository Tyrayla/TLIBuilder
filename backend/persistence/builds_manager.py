import json
import os
import uuid

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_DIR = os.path.normpath(os.path.join(_DATA_ROOT, 'builds'))


def _file(build_id: str) -> str:
    return os.path.join(_DIR, f"{build_id}.txt")


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
    with open(_file(build_id)) as f:
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

    hero_memories_raw = data.get('hero_memories', '')
    hero_memories = json.loads(hero_memories_raw) if hero_memories_raw else [None, None, None]

    pact_spirits_raw = data.get('pact_spirits', '')
    pact_spirits = json.loads(pact_spirits_raw) if pact_spirits_raw else [None, None, None]

    notes_raw = data.get('notes', '')
    notes = json.loads(notes_raw) if notes_raw else ''

    return {
        'id': data.get('id', build_id),
        'name': data.get('name', ''),
        'slots': slots,
        'slates': slates,
        'conditions': conditions,
        'conditionValues': condition_values,
        'gear': gear,
        'skills': skills,
        'characterLevel': character_level,
        'hasPrism': has_prism,
        'traitId': trait_id,
        'traitLevel': trait_level,
        'traitSlotLevels': trait_slot_levels,
        'advancedTraitSelections': advanced_trait_selections,
        'heroMemories': hero_memories,
        'pactSpirits': pact_spirits,
        'notes': notes,
    }


def _write_file(build: dict) -> None:
    os.makedirs(_DIR, exist_ok=True)
    slots = build.get('slots') or [None, None, None, None]
    slates = build.get('slates') or []
    with open(_file(build['id']), 'w') as f:
        f.write(f"id={build['id']}\n")
        f.write(f"name={build['name']}\n")
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
        hero_memories = build.get('heroMemories') or [None, None, None]
        f.write(f"hero_memories={json.dumps(hero_memories, separators=(',', ':'))}\n")
        pact_spirits = build.get('pactSpirits') or [None, None, None]
        f.write(f"pact_spirits={json.dumps(pact_spirits, separators=(',', ':'))}\n")
        notes = build.get('notes') or ''
        f.write(f"notes={json.dumps(notes, separators=(',', ':'))}\n")


def load() -> list[dict]:
    if not os.path.isdir(_DIR):
        return []
    builds = []
    for fname in sorted(os.listdir(_DIR)):
        if fname.endswith('.txt'):
            try:
                builds.append(_read_file(fname[:-4]))
            except Exception:
                pass
    return builds


def save_build(build: dict) -> dict:
    if not build.get('id'):
        build['id'] = str(uuid.uuid4())[:8]
    _write_file(build)
    return build


def delete_build(build_id: str) -> bool:
    path = _file(build_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True
