"""
Diffs two talent snapshots produced by talent_parser.parse_document().

Regular nodes  → matched by position (index) within each tree + node_type.
Core talents   → matched by name within each tree (order-independent).
New-God talents → matched by name (order-independent).

Stats are dicts with at least {"text": str} and optionally {"max_divinity_effect": true}.
A stat is "changed" when either the text or the max_divinity_effect flag differs.
"""

from __future__ import annotations


def _stat_key(s: dict) -> str:
    flag = " [MAX_DIV]" if s.get("max_divinity_effect") else ""
    return s.get("text", "") + flag


def _stats_equal(a: list[dict], b: list[dict]) -> bool:
    return [_stat_key(s) for s in a] == [_stat_key(s) for s in b]


# ── Regular nodes (positional) ───────────────────────────────────────────────

def _diff_nodes(nodes_a: list[dict], nodes_b: list[dict]) -> tuple[list[dict], bool]:
    max_len = max(len(nodes_a), len(nodes_b)) if (nodes_a or nodes_b) else 0
    results = []
    changed = False

    for i in range(max_len):
        na = nodes_a[i] if i < len(nodes_a) else None
        nb = nodes_b[i] if i < len(nodes_b) else None

        if na is None:
            results.append({"index": i, "node_type": nb["node_type"],
                             "status": "added", "stats_a": None, "stats_b": nb["stats"]})
            changed = True
        elif nb is None:
            results.append({"index": i, "node_type": na["node_type"],
                             "status": "removed", "stats_a": na["stats"], "stats_b": None})
            changed = True
        elif not _stats_equal(na["stats"], nb["stats"]) or na["node_type"] != nb["node_type"]:
            results.append({"index": i, "node_type": nb["node_type"],
                             "status": "changed", "stats_a": na["stats"], "stats_b": nb["stats"]})
            changed = True
        else:
            results.append({"index": i, "node_type": na["node_type"],
                             "status": "unchanged", "stats_a": na["stats"], "stats_b": nb["stats"]})

    return results, changed


# ── Named talents (core talents & new-god) ───────────────────────────────────

def _diff_named(items_a: list[dict], items_b: list[dict],
                label: str = "name") -> tuple[list[dict], bool]:
    """Diff two lists of named talent dicts keyed by their 'name' field."""
    map_a = {t[label]: t for t in items_a}
    map_b = {t[label]: t for t in items_b}
    all_names = sorted(set(map_a) | set(map_b))
    results = []
    changed = False

    for name in all_names:
        ta = map_a.get(name)
        tb = map_b.get(name)

        if ta is None:
            results.append({"name": name, "status": "added",
                             "stats_a": None, "stats_b": tb["stats"]})
            changed = True
        elif tb is None:
            results.append({"name": name, "status": "removed",
                             "stats_a": ta["stats"], "stats_b": None})
            changed = True
        elif not _stats_equal(ta["stats"], tb["stats"]):
            results.append({"name": name, "status": "changed",
                             "stats_a": ta["stats"], "stats_b": tb["stats"]})
            changed = True
        else:
            results.append({"name": name, "status": "unchanged",
                             "stats_a": ta["stats"], "stats_b": tb["stats"]})

    return results, changed


# ── Top-level diff ───────────────────────────────────────────────────────────

def diff_snapshots(snap_a: dict, snap_b: dict) -> dict:
    """
    Returns a structured diff:

    {
      "summary": {
        "trees_added": int, "trees_removed": int,
        "nodes_added": int, "nodes_removed": int, "nodes_changed": int,
        "core_talents_added": int, "core_talents_removed": int, "core_talents_changed": int,
        "new_god_added": int, "new_god_removed": int, "new_god_changed": int,
      },
      "trees": {
        "Tree Name": {
          "status": "added"|"removed"|"changed"|"unchanged",
          "nodes": [ {index, node_type, status, stats_a, stats_b}, ... ],
          "core_talents": [ {name, status, stats_a, stats_b}, ... ],
        }
      },
      "new_god_talents": [ {name, status, stats_a, stats_b}, ... ]
    }
    """
    trees_a: dict = snap_a.get("trees", {})
    trees_b: dict = snap_b.get("trees", {})
    new_god_a: list = snap_a.get("new_god_talents", [])
    new_god_b: list = snap_b.get("new_god_talents", [])

    summary: dict = {
        "trees_added": 0, "trees_removed": 0,
        "nodes_added": 0, "nodes_removed": 0, "nodes_changed": 0,
        "core_talents_added": 0, "core_talents_removed": 0, "core_talents_changed": 0,
        "new_god_added": 0, "new_god_removed": 0, "new_god_changed": 0,
    }
    result_trees: dict = {}

    for tree_name in sorted(set(trees_a) | set(trees_b)):
        in_a = tree_name in trees_a
        in_b = tree_name in trees_b

        if not in_a:
            ta = {"nodes": [], "core_talents": []}
            tb = trees_b[tree_name]
            summary["trees_added"] += 1
        elif not in_b:
            ta = trees_a[tree_name]
            tb = {"nodes": [], "core_talents": []}
            summary["trees_removed"] += 1
        else:
            ta = trees_a[tree_name]
            tb = trees_b[tree_name]

        node_results, nodes_changed = _diff_nodes(ta.get("nodes", []), tb.get("nodes", []))
        ct_results, cts_changed = _diff_named(ta.get("core_talents", []), tb.get("core_talents", []))

        for n in node_results:
            if n["status"] == "added":   summary["nodes_added"] += 1
            elif n["status"] == "removed": summary["nodes_removed"] += 1
            elif n["status"] == "changed": summary["nodes_changed"] += 1

        for ct in ct_results:
            if ct["status"] == "added":    summary["core_talents_added"] += 1
            elif ct["status"] == "removed": summary["core_talents_removed"] += 1
            elif ct["status"] == "changed": summary["core_talents_changed"] += 1

        tree_changed = nodes_changed or cts_changed
        if not in_a:
            tree_status = "added"
        elif not in_b:
            tree_status = "removed"
        else:
            tree_status = "changed" if tree_changed else "unchanged"

        result_trees[tree_name] = {
            "status": tree_status,
            "nodes": node_results,
            "core_talents": ct_results,
        }

    # New-God diff
    new_god_results, _ = _diff_named(new_god_a, new_god_b)
    for ng in new_god_results:
        if ng["status"] == "added":    summary["new_god_added"] += 1
        elif ng["status"] == "removed": summary["new_god_removed"] += 1
        elif ng["status"] == "changed": summary["new_god_changed"] += 1

    return {"summary": summary, "trees": result_trees, "new_god_talents": new_god_results}
