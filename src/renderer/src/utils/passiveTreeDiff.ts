// Pure helpers for the passive-tree hover preview (TreeViewerScreen): the prereq-satisfaction
// threshold, before/after node-state diffing, and a cache-key signature for a full node-states map.
// Extracted out of TreeViewerScreen.tsx so they're independently unit-testable (see utils/talentPoints.ts
// for the precedent on this class of tree-points helper).

/**
 * Every incoming source needs this many points before it satisfies a prereq edge — mirrors
 * `backend/models/passive_tree.py`'s `_prereq_threshold` (node_type only; NOT the same thing as
 * the node's own `max_points`, which varies per node and can differ from this — see
 * `backend/models/passive_node.py`'s `max_points` comment and
 * `backend/tests/test_passive_tree.py::test_deallocate_source_above_threshold_ok`, which exercises
 * a node with `max_points=5, threshold=3` specifically to pin that the two are independent).
 * No currently-shipped tree has a divergent node (threshold == max_points for every shipped node
 * today), but nothing here — or in TreeViewerScreen's allocate/deallocate/cascade logic, which
 * always gates on this threshold rather than `max_points` — assumes that stays true.
 */
export function nodeThreshold(n: { node_type: string }): number {
  return n.node_type === 'Legendary Medium Talent' ? 1 : 3
}

/** Diff two node-state maps: ids whose point count INCREASED from `before` to `after` (with the delta). */
export function diffAdded(
  before: Record<string, number>, after: Record<string, number>,
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const id of Object.keys(after)) {
    const b = before[id] ?? 0, a = after[id]
    if (a > b) out[id] = a - b
  }
  return out
}

/** Diff two node-state maps: ids whose point count DECREASED from `before` to `after` (with the delta). */
export function diffRemoved(
  before: Record<string, number>, after: Record<string, number>,
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const id of Object.keys(before)) {
    const b = before[id], a = after[id] ?? 0
    if (a < b) out[id] = b - a
  }
  return out
}

/**
 * A stable, order-independent signature of a complete node-states map, for use as a `useDamageDelta`
 * cache key. The hover preview prices a MULTI-node change (a forward path-fill or a reverse cascade),
 * so the key must identify the resulting STATE, not just its point-total cost — two different paths to
 * the same node can legitimately cost the same total points while landing on different node-state maps,
 * and a cost-only key would collide the two (see bug-142 in .wolf/buglog.json).
 */
export function nodeStatesSignature(states: Record<string, number>): string {
  return Object.keys(states).sort().map(id => `${id}:${states[id]}`).join(',')
}
