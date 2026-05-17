from typing import Dict, List
from models.passive_node import PassiveNode

COLUMN_COUNT = 7          # columns 0-6, displayed as 0, 3, 6, 9, 12, 15, 18
COLUMN_UNLOCK_THRESHOLD = 3  # points needed in previous column to unlock next


class PassiveTree:
    def __init__(self, name: str):
        self.name = name
        self.nodes: Dict[str, PassiveNode] = {}

    def add_node(self, node: PassiveNode):
        self.nodes[node.id] = node

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
        return self.points_in_column(col - 1) >= COLUMN_UNLOCK_THRESHOLD

    def total_points(self) -> int:
        return sum(n.current_points for n in self.nodes.values())

    def allocate(self, node_id: str):
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")
        if not self.is_column_unlocked(node.column):
            prev_label = (node.column - 1) * 3
            have = self.points_in_column(node.column - 1)
            raise ValueError(
                f"Column {node.column_label} is locked. "
                f"Need {COLUMN_UNLOCK_THRESHOLD} pts in column {prev_label}, have {have}."
            )
        if node.is_full:
            raise ValueError(f"'{node.node_type.value}' is already at max ({node.max_points}/{node.max_points}).")
        node.current_points += 1

    def deallocate(self, node_id: str):
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")
        if node.is_empty:
            raise ValueError(f"'{node.node_type.value}' already has 0 points.")
        # Check: removing this point must not break a column that depends on it
        if not self._can_remove_point(node):
            raise ValueError(
                f"Cannot remove: column {node.column_label + 3} "
                f"would lose access (it has points allocated)."
            )
        node.current_points -= 1

    def _can_remove_point(self, node: PassiveNode) -> bool:
        # If removing 1 point from this column would drop it below the unlock threshold,
        # and the next column has points allocated, the removal is blocked.
        next_col = node.column + 1
        if next_col >= COLUMN_COUNT:
            return True
        current_col_pts = self.points_in_column(node.column)
        if current_col_pts - 1 < COLUMN_UNLOCK_THRESHOLD:
            if self.points_in_column(next_col) > 0:
                return False
        return True
