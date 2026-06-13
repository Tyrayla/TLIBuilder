"""
Tests: models/passive_tree.py — the "preceding-columns" column-unlock rule plus connection
prerequisites for allocate() / deallocate().

Rule under test: column 0 is always open; column N (display label N*3) requires N*3 points
spent in columns strictly to its LEFT. A point counts toward unlocking only columns to its
right, so removing it can only strand those. Connection prerequisites: a destination node
needs its source(s) at >= _prereq_threshold (1 for LEGENDARY_MEDIUM, else 3).
"""
import pytest
from models.passive_node import PassiveNode, NodeType
from models.passive_tree import PassiveTree


def _node(col, row, max_points=3, node_type=NodeType.MICRO, points=0):
    return PassiveNode(
        id=f"n_c{col}_r{row}", node_type=node_type, column=col, row=row,
        max_points=max_points, current_points=points,
    )


def _tree(nodes, connections=None):
    t = PassiveTree("test")
    for n in nodes:
        t.add_node(n)
    for a, b in (connections or []):
        t.add_connection(a, b)
    return t


# ── Column unlock (preceding-columns) ──────────────────────────────────────────

class TestColumnUnlock:
    def test_col0_always_unlocked(self):
        assert _tree([_node(0, 0)]).is_column_unlocked(0)

    def test_col1_requires_3_in_col0(self):
        a, b = _node(0, 0), _node(1, 0)
        t = _tree([a, b])
        assert not t.is_column_unlocked(1)
        a.current_points = 2
        assert not t.is_column_unlocked(1)
        a.current_points = 3
        assert t.is_column_unlocked(1)

    def test_col2_requires_6_in_preceding_columns(self):
        a, b, c = _node(0, 0), _node(1, 0), _node(2, 0)
        t = _tree([a, b, c])
        a.current_points, b.current_points = 3, 3   # 6 preceding
        assert t.is_column_unlocked(2)
        b.current_points = 2                          # 5 preceding
        assert not t.is_column_unlocked(2)

    def test_own_column_points_do_not_unlock_self(self):
        # Points sitting IN column 1 must not count toward unlocking column 1.
        a, b = _node(0, 0, points=0), _node(1, 0, points=3)
        assert not _tree([a, b]).is_column_unlocked(1)

    def test_further_right_points_do_not_count(self):
        # A loaded column 2 must not help unlock column 1.
        a, b, c = _node(0, 0), _node(1, 0), _node(2, 0, points=3)
        assert not _tree([a, b, c]).is_column_unlocked(1)

    def test_points_before_column(self):
        a, b, c = _node(0, 0, points=2), _node(1, 0, points=3), _node(2, 0, points=1)
        t = _tree([a, b, c])
        assert t.points_before_column(0) == 0
        assert t.points_before_column(1) == 2
        assert t.points_before_column(2) == 5
        assert t.points_before_column(3) == 6


# ── allocate() ─────────────────────────────────────────────────────────────────

class TestAllocate:
    def test_allocate_col0_is_free(self):
        a = _node(0, 0)
        t = _tree([a])
        t.allocate(a.id)
        assert a.current_points == 1

    def test_allocate_locked_column_raises(self):
        a, b = _node(0, 0, points=2), _node(1, 0)
        with pytest.raises(ValueError):
            _tree([a, b]).allocate(b.id)

    def test_allocate_unlocked_column_ok(self):
        a, b = _node(0, 0, points=3), _node(1, 0)
        t = _tree([a, b])
        t.allocate(b.id)
        assert b.current_points == 1

    def test_allocate_full_node_raises(self):
        a = _node(0, 0, max_points=3, points=3)
        with pytest.raises(ValueError):
            _tree([a]).allocate(a.id)

    def test_allocate_unknown_node_raises(self):
        with pytest.raises(ValueError):
            _tree([]).allocate("missing")

    def test_connection_prereq_normal_requires_3(self):
        src, dst = _node(0, 0), _node(0, 1)   # both col0 (unlocked); dst depends on src
        t = _tree([src, dst], [(src.id, dst.id)])
        with pytest.raises(ValueError):
            t.allocate(dst.id)                # src has 0
        src.current_points = 3
        t.allocate(dst.id)
        assert dst.current_points == 1

    def test_connection_prereq_legendary_requires_1(self):
        src = _node(0, 0, node_type=NodeType.LEGENDARY_MEDIUM, max_points=1)
        dst = _node(0, 1)
        t = _tree([src, dst], [(src.id, dst.id)])
        with pytest.raises(ValueError):
            t.allocate(dst.id)                # src has 0
        src.current_points = 1
        t.allocate(dst.id)
        assert dst.current_points == 1

    def test_multiple_sources_all_required(self):
        s1, s2, dst = _node(0, 0), _node(0, 1), _node(0, 2)
        t = _tree([s1, s2, dst], [(s1.id, dst.id), (s2.id, dst.id)])
        s1.current_points = 3
        with pytest.raises(ValueError):
            t.allocate(dst.id)                # s2 still 0
        s2.current_points = 3
        t.allocate(dst.id)
        assert dst.current_points == 1


# ── deallocate() ─────────────────────────────────────────────────────────────────

class TestDeallocate:
    def test_deallocate_empty_raises(self):
        with pytest.raises(ValueError):
            _tree([_node(0, 0, points=0)]).deallocate("n_c0_r0")

    def test_deallocate_basic(self):
        a = _node(0, 0, points=2)
        t = _tree([a])
        t.deallocate(a.id)
        assert a.current_points == 1

    def test_deallocate_strands_right_column_blocked(self):
        a, b = _node(0, 0, points=3), _node(1, 0, points=1)
        # Removing a col0 point drops preceding(col1) 3->2 < 3 while col1 is occupied.
        with pytest.raises(ValueError):
            _tree([a, b]).deallocate(a.id)

    def test_deallocate_safe_when_right_column_empty(self):
        a, b = _node(0, 0, points=3), _node(1, 0, points=0)
        t = _tree([a, b])
        t.deallocate(a.id)
        assert a.current_points == 2

    def test_deallocate_safe_with_buffer(self):
        a, a2, b = _node(0, 0, points=3), _node(0, 1, points=1), _node(1, 0, points=1)
        t = _tree([a, a2, b])   # preceding(col1) = 4; removing one leaves 3 >= 3
        t.deallocate(a.id)
        assert a.current_points == 2

    def test_deallocate_within_column_not_blocked_by_self(self):
        # Removing a point from column 1 only checks columns to its RIGHT (none here).
        a, b = _node(0, 0, points=3), _node(1, 0, points=2)
        t = _tree([a, b])
        t.deallocate(b.id)
        assert b.current_points == 1

    def test_deallocate_does_not_check_left_columns(self):
        # Removing from column 2 must not be blocked by columns to its left.
        a, b, c = _node(0, 0, points=3), _node(1, 0, points=3), _node(2, 0, points=2)
        t = _tree([a, b, c])
        t.deallocate(c.id)
        assert c.current_points == 1

    def test_deallocate_connection_prereq_blocks(self):
        src, dst = _node(0, 0, points=3), _node(0, 1, points=1)
        # src 3->2 falls below threshold 3 while dependent dst is occupied.
        with pytest.raises(ValueError):
            _tree([src, dst], [(src.id, dst.id)]).deallocate(src.id)

    def test_deallocate_connection_prereq_ok_when_dependent_empty(self):
        src, dst = _node(0, 0, points=3), _node(0, 1, points=0)
        t = _tree([src, dst], [(src.id, dst.id)])
        t.deallocate(src.id)
        assert src.current_points == 2

    def test_deallocate_connection_legendary_threshold_1(self):
        src = _node(0, 0, node_type=NodeType.LEGENDARY_MEDIUM, max_points=1, points=1)
        dst = _node(0, 1, points=1)
        # src 1->0 falls below legendary threshold 1 while dst is occupied.
        with pytest.raises(ValueError):
            _tree([src, dst], [(src.id, dst.id)]).deallocate(src.id)

    def test_deallocate_source_above_threshold_ok(self):
        src, dst = _node(0, 0, max_points=5, points=4), _node(0, 1, points=1)
        t = _tree([src, dst], [(src.id, dst.id)])
        t.deallocate(src.id)              # 4->3 still meets threshold 3
        assert src.current_points == 3


# ── End-to-end scenarios ─────────────────────────────────────────────────────────

class TestScenarios:
    def test_allocate_chain_then_strand_on_removal(self):
        a, b = _node(0, 0, max_points=3), _node(1, 0, max_points=3)
        t = _tree([a, b])
        for _ in range(3):
            t.allocate(a.id)             # col0 -> 3, unlocking col1
        t.allocate(b.id)
        assert b.current_points == 1
        with pytest.raises(ValueError):
            t.deallocate(a.id)          # removing would strand col1
        # Emptying col1 first makes the col0 removal legal again.
        t.deallocate(b.id)
        t.deallocate(a.id)
        assert a.current_points == 2

    def test_unwind_in_reverse_is_always_legal(self):
        a, b, c = _node(0, 0, points=3), _node(1, 0, points=3), _node(2, 0, points=2)
        t = _tree([a, b, c])
        # Removing right-to-left never strands anything to the right.
        t.deallocate(c.id); t.deallocate(c.id)
        for _ in range(3):
            t.deallocate(b.id)
        for _ in range(3):
            t.deallocate(a.id)
        assert t.total_points() == 0
