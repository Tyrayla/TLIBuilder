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

    def is_column_unlocked(self, col: int) -> bool:
        if col == 0:
            return True
        return self.total_points() >= col * 3

    def total_points(self) -> int:
        return sum(n.current_points for n in self.nodes.values())

    def allocate(self, node_id: str):
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")
        if not self.is_column_unlocked(node.column):
            needed = node.column * 3
            have = self.total_points()
            raise ValueError(
                f"Column {node.column_label} is locked. "
                f"Need {needed} total points, have {have}."
            )
        if node.is_full:
            raise ValueError(
                f"'{node.node_type.value}' is already at max ({node.max_points}/{node.max_points}).")

        # Connection prerequisite: every source node pointing to this node must
        # meet its threshold before this node can receive any points.
        for id1, id2 in self.connections:
            if id2 == node_id:
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

    def deallocate(self, node_id: str):
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")
        if node.is_empty:
            raise ValueError(f"'{node.node_type.value}' already has 0 points.")

        # Column unlock check: removing a point must not strand any occupied column.
        total_after = self.total_points() - 1
        for col in range(1, COLUMN_COUNT):
            if self.points_in_column(col) > 0 and total_after < col * 3:
                raise ValueError(
                    f"Cannot remove: column {col * 3} requires "
                    f"{col * 3} total points (would have {total_after})."
                )

        # Connection prerequisite check: removing a point from this node must not
        # drop it below the threshold required by any node it feeds into.
        needed = _prereq_threshold(node)
        if node.current_points - 1 < needed:
            for id1, id2 in self.connections:
                if id1 == node_id:
                    dep = self.nodes.get(id2)
                    if dep and not dep.is_empty:
                        raise ValueError(
                            f"Cannot remove: '{dep.node_type.value}' depends on "
                            f"this node having ≥{needed} pt(s)."
                        )

        node.current_points -= 1
