from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType


def build_tree() -> PassiveTree:
    tree = PassiveTree("Machinist")

    # Column 0 (label: 0)
    tree.add_node(PassiveNode(id="machinist_c0_r0", node_type=NodeType.MICRO, column=0, row=0, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c0_r2", node_type=NodeType.MICRO, column=0, row=2, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c0_r4", node_type=NodeType.MICRO, column=0, row=4, max_points=3))

    # Column 1 (label: 3)
    tree.add_node(PassiveNode(id="machinist_c1_r0", node_type=NodeType.MEDIUM,  column=1, row=0, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c1_r1", node_type=NodeType.MICRO,  column=1, row=1, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c1_r2", node_type=NodeType.MEDIUM, column=1, row=2, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c1_r3", node_type=NodeType.MICRO,  column=1, row=3, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c1_r4", node_type=NodeType.MEDIUM,  column=1, row=4, max_points=3))

    # Column 2 (label: 6)
    tree.add_node(PassiveNode(id="machinist_c2_r0", node_type=NodeType.MICRO,            column=2, row=0, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c2_r1", node_type=NodeType.MEDIUM, column=2, row=1, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c2_r2", node_type=NodeType.MICRO,            column=2, row=2, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c2_r3", node_type=NodeType.MEDIUM,            column=2, row=3, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c2_r4", node_type=NodeType.MICRO,            column=2, row=4, max_points=3))

    # Column 3 (label: 9) — no row 1
    tree.add_node(PassiveNode(id="machinist_c3_r0", node_type=NodeType.MEDIUM,  column=3, row=0, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c3_r2", node_type=NodeType.MEDIUM, column=3, row=2, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c3_r3", node_type=NodeType.LEGENDARY_MEDIUM,  column=3, row=3, max_points=1))
    tree.add_node(PassiveNode(id="machinist_c3_r4", node_type=NodeType.MEDIUM,  column=3, row=4, max_points=3))

    # Column 4 (label: 12)
    tree.add_node(PassiveNode(id="machinist_c4_r0", node_type=NodeType.MICRO,  column=4, row=0, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c4_r1", node_type=NodeType.MICRO,  column=4, row=1, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c4_r2", node_type=NodeType.MICRO, column=4, row=2, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c4_r3", node_type=NodeType.MICRO,  column=4, row=3, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c4_r4", node_type=NodeType.MICRO,  column=4, row=4, max_points=3))

    # Column 5 (label: 15)
    tree.add_node(PassiveNode(id="machinist_c5_r0", node_type=NodeType.MEDIUM,  column=5, row=0, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c5_r1", node_type=NodeType.MEDIUM,  column=5, row=1, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c5_r2", node_type=NodeType.MEDIUM, column=5, row=2, max_points=3))
    tree.add_node(PassiveNode(id="machinist_c5_r3", node_type=NodeType.LEGENDARY_MEDIUM,  column=5, row=3, max_points=1))
    tree.add_node(PassiveNode(id="machinist_c5_r4", node_type=NodeType.LEGENDARY_MEDIUM,  column=5, row=4, max_points=1))

    # Column 6 (label: 18) — rows 0, 1 only
    tree.add_node(PassiveNode(id="machinist_c6_r0", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=0, max_points=1))
    tree.add_node(PassiveNode(id="machinist_c6_r1", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=1, max_points=1))

    # ── Connections ────────────────────────────────────────────────────────────
    # tree.add_connection("machinist_cCOL_rROW", "machinist_cCOL_rROW")

    tree.add_connection("machinist_c0_r0", "machinist_c1_r0")
    tree.add_connection("machinist_c0_r2", "machinist_c1_r2")
    tree.add_connection("machinist_c0_r4", "machinist_c1_r4")
    tree.add_connection("machinist_c1_r3", "machinist_c2_r3")
    tree.add_connection("machinist_c2_r3", "machinist_c3_r3")
    tree.add_connection("machinist_c2_r4", "machinist_c3_r4")
    tree.add_connection("machinist_c2_r2", "machinist_c3_r2")
    tree.add_connection("machinist_c1_r1", "machinist_c2_r1")
    tree.add_connection("machinist_c2_r0", "machinist_c3_r0")
    tree.add_connection("machinist_c4_r0", "machinist_c5_r0")
    tree.add_connection("machinist_c5_r0", "machinist_c6_r0")
    tree.add_connection("machinist_c4_r1", "machinist_c5_r1")
    tree.add_connection("machinist_c5_r1", "machinist_c6_r1")
    tree.add_connection("machinist_c4_r2", "machinist_c5_r2")
    tree.add_connection("machinist_c4_r3", "machinist_c5_r3")
    tree.add_connection("machinist_c4_r4", "machinist_c5_r4")
    return tree
