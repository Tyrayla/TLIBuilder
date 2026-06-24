from typing import Dict, List
from models.passive_node import PassiveNode, NodeType
from models.core_talent import CoreTalentSlot

COLUMN_COUNT = 7          # columns 0-6, displayed as 0, 3, 6, 9, 12, 15, 18


def _prereq_threshold(node: PassiveNode) -> int:
    """Points required in a source node before its connected destination can be allocated."""
    return 1 if node.node_type == NodeType.LEGENDARY_MEDIUM else 3


class PassiveTree:
    def __init__(self, name: str):
        self.name = name
        self.nodes: Dict[str, PassiveNode] = {}
        self.connections: list[tuple[str, str]] = []
        self.core_talent_slots: list[CoreTalentSlot] = []

    def add_node(self, node: PassiveNode):
        self.nodes[node.id] = node

    def add_connection(self, id1: str, id2: str):
        self.connections.append((id1, id2))

    def add_core_talent_slot(self, slot: CoreTalentSlot):
        self.core_talent_slots.append(slot)

    def nodes_in_column(self, col: int) -> List[PassiveNode]:
        return sorted(
            [n for n in self.nodes.values() if n.column == col],
            key=lambda n: n.row,
        )

    def points_in_column(self, col: int) -> int:
        return sum(n.current_points for n in self.nodes.values() if n.column == col)

    def points_before_column(self, col: int) -> int:
        """Points spent in columns strictly to the LEFT of `col` (the unlock currency)."""
        return sum(n.current_points for n in self.nodes.values() if n.column < col)

    def is_column_unlocked(self, col: int) -> bool:
        # Column 0 is always open; column N needs N*3 points spent in columns to its left
        # (its own points and points further right do not count toward unlocking it).
        if col == 0:
            return True
        return self.points_before_column(col) >= col * 3

    def total_points(self) -> int:
        return sum(n.current_points for n in self.nodes.values())

    def allocate(self, node_id: str, prereq_satisfied: set[str] | None = None,
                 max_overrides: dict[str, int] | None = None):
        # `prereq_satisfied` = node ids whose OUTGOING connection prerequisites are treated as met regardless of
        # their points (a Prism's overridden anchor + its reflected-box cells break the prereq chain there).
        # `max_overrides` = node id → raised max-point cap (an Ethereal Prism's over-allocation affix). Only the
        # headroom for extra points grows; the prereq threshold (_prereq_threshold) is untouched.
        prereq_satisfied = prereq_satisfied or set()
        max_overrides = max_overrides or {}
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")
        if not self.is_column_unlocked(node.column):
            needed = node.column * 3
            have = self.points_before_column(node.column)
            raise ValueError(
                f"Column {node.column_label} is locked. "
                f"Need {needed} points in earlier columns, have {have}."
            )
        eff_max = max_overrides.get(node_id, node.max_points)
        if node.current_points >= eff_max:
            raise ValueError(
                f"'{node.node_type.value}' is already at max ({node.current_points}/{eff_max}).")

        # Connection prerequisite: every source node pointing to this node must
        # meet its threshold before this node can receive any points.
        for id1, id2 in self.connections:
            if id2 == node_id:
                if id1 in prereq_satisfied:
                    continue                 # prereq chain broken here by a Prism
                prereq = self.nodes.get(id1)
                if prereq is not None:
                    needed = _prereq_threshold(prereq)
                    if prereq.current_points < needed:
                        raise ValueError(
                            f"Requires the connected '{prereq.node_type.value}' "
                            f"to have ≥{needed} pt(s) first "
                            f"(currently {prereq.current_points}/{prereq.max_points})."
                        )

        node.current_points += 1

    def deallocate(self, node_id: str, prereq_satisfied: set[str] | None = None):
        prereq_satisfied = prereq_satisfied or set()
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")
        if node.is_empty:
            raise ValueError(f"'{node.node_type.value}' already has 0 points.")

        # Column unlock check: a point in this column counts toward unlocking every column to
        # its RIGHT, so removing it can only strand those. (Columns at or left of node.column
        # don't count this point, so they're unaffected.)
        for col in range(node.column + 1, COLUMN_COUNT):
            if self.points_in_column(col) > 0 and (self.points_before_column(col) - 1) < col * 3:
                raise ValueError(
                    f"Cannot remove: column {col * 3} requires {col * 3} points in earlier "
                    f"columns (would have {self.points_before_column(col) - 1})."
                )

        # Connection prerequisite check: removing a point from this node must not
        # drop it below the threshold required by any node it feeds into.
        needed = _prereq_threshold(node)
        if node.current_points - 1 < needed and node_id not in prereq_satisfied:
            for id1, id2 in self.connections:
                if id1 == node_id:
                    dep = self.nodes.get(id2)
                    if dep and not dep.is_empty:
                        raise ValueError(
                            f"Cannot remove: '{dep.node_type.value}' depends on "
                            f"this node having ≥{needed} pt(s)."
                        )

        node.current_points -= 1
