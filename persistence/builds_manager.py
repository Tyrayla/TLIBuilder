import os
import uuid

_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data', 'builds'))


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
            slots.append({'treeName': tree, 'nodeStates': nodes})
        else:
            slots.append(None)

    return {
        'id': data.get('id', build_id),
        'name': data.get('name', ''),
        'slots': slots,
    }


def _write_file(build: dict) -> None:
    os.makedirs(_DIR, exist_ok=True)
    slots = build.get('slots') or [None, None, None, None]
    with open(_file(build['id']), 'w') as f:
        f.write(f"id={build['id']}\n")
        f.write(f"name={build['name']}\n")
        for i, slot in enumerate(slots, 1):
            if slot:
                tree = slot.get('treeName', '')
                node_states = slot.get('nodeStates', {})
                nodes_str = ','.join(f"{k}:{v}" for k, v in node_states.items() if v > 0)
            else:
                tree = ''
                nodes_str = ''
            f.write(f"slot{i}_tree={tree}\n")
            f.write(f"slot{i}_nodes={nodes_str}\n")


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
