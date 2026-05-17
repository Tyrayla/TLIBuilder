from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType


def build_tree() -> PassiveTree:
    tree = PassiveTree("Druid")

    # Column 0 (label: 0)
    tree.add_node(PassiveNode(id="druid_c0_r0", node_type=NodeType.MICRO, column=0, row=0, max_points=3))
    tree.add_node(PassiveNode(id="druid_c0_r2", node_type=NodeType.MICRO, column=0, row=2, max_points=3))
    tree.add_node(PassiveNode(id="druid_c0_r4", node_type=NodeType.MICRO, column=0, row=4, max_points=3))

    # Column 1 (label: 3)
    tree.add_node(PassiveNode(id="druid_c1_r0", node_type=NodeType.MEDIUM,  column=1, row=0, max_points=3))
    tree.add_node(PassiveNode(id="druid_c1_r1", node_type=NodeType.MICRO,  column=1, row=1, max_points=3))
    tree.add_node(PassiveNode(id="druid_c1_r2", node_type=NodeType.MEDIUM, column=1, row=2, max_points=3))
    tree.add_node(PassiveNode(id="druid_c1_r3", node_type=NodeType.MICRO,  column=1, row=3, max_points=3))
    tree.add_node(PassiveNode(id="druid_c1_r4", node_type=NodeType.MEDIUM,  column=1, row=4, max_points=3))

    # Column 2 (label: 6) — rows 0-3 only
    tree.add_node(PassiveNode(id="druid_c2_r0", node_type=NodeType.MICRO,            column=2, row=0, max_points=3))
    tree.add_node(PassiveNode(id="druid_c2_r1", node_type=NodeType.MEDIUM, column=2, row=1, max_points=3))
    tree.add_node(PassiveNode(id="druid_c2_r2", node_type=NodeType.MICRO,            column=2, row=2, max_points=3))
    tree.add_node(PassiveNode(id="druid_c2_r3", node_type=NodeType.MEDIUM,            column=2, row=3, max_points=3))

    # Column 3 (label: 9) — no row 1
    tree.add_node(PassiveNode(id="druid_c3_r0", node_type=NodeType.MEDIUM,  column=3, row=0, max_points=3))
    tree.add_node(PassiveNode(id="druid_c3_r2", node_type=NodeType.MEDIUM, column=3, row=2, max_points=3))
    tree.add_node(PassiveNode(id="druid_c3_r3", node_type=NodeType.MICRO,  column=3, row=3, max_points=3))
    tree.add_node(PassiveNode(id="druid_c3_r4", node_type=NodeType.MICRO,  column=3, row=4, max_points=3))

    # Column 4 (label: 12)
    tree.add_node(PassiveNode(id="druid_c4_r0", node_type=NodeType.MICRO,  column=4, row=0, max_points=3))
    tree.add_node(PassiveNode(id="druid_c4_r1", node_type=NodeType.LEGENDARY_MEDIUM,  column=4, row=1, max_points=1))
    tree.add_node(PassiveNode(id="druid_c4_r2", node_type=NodeType.LEGENDARY_MEDIUM, column=4, row=2, max_points=1))
    tree.add_node(PassiveNode(id="druid_c4_r3", node_type=NodeType.LEGENDARY_MEDIUM,  column=4, row=3, max_points=1))
    tree.add_node(PassiveNode(id="druid_c4_r4", node_type=NodeType.LEGENDARY_MEDIUM,  column=4, row=4, max_points=1))

    # Column 5 (label: 15) — rows 0, 1, 2 only
    tree.add_node(PassiveNode(id="druid_c5_r0", node_type=NodeType.MEDIUM,  column=5, row=0, max_points=3))
    tree.add_node(PassiveNode(id="druid_c5_r1", node_type=NodeType.MEDIUM,  column=5, row=1, max_points=3))
    tree.add_node(PassiveNode(id="druid_c5_r2", node_type=NodeType.MICRO, column=5, row=2, max_points=3))

    # Column 6 (label: 18) — rows 0, 1, 2 only
    tree.add_node(PassiveNode(id="druid_c6_r0", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=0, max_points=1))
    tree.add_node(PassiveNode(id="druid_c6_r1", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=1, max_points=1))
    tree.add_node(PassiveNode(id="druid_c6_r2", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=2, max_points=1))

    # ── Connections ────────────────────────────────────────────────────────────
    # tree.add_connection("druid_cCOL_rROW", "druid_cCOL_rROW")

    tree.add_connection("druid_c0_r0", "druid_c1_r0")
    tree.add_connection("druid_c0_r2", "druid_c1_r2")
    tree.add_connection("druid_c0_r4", "druid_c1_r4")
    tree.add_connection("druid_c1_r3", "druid_c2_r3")
    tree.add_connection("druid_c2_r2", "druid_c3_r2")
    tree.add_connection("druid_c3_r2", "druid_c4_r1")
    tree.add_connection("druid_c3_r2", "druid_c4_r2")
    tree.add_connection("druid_c3_r3", "druid_c4_r3")
    tree.add_connection("druid_c3_r4", "druid_c4_r4")
    tree.add_connection("druid_c1_r1", "druid_c2_r1")
    tree.add_connection("druid_c2_r0", "druid_c3_r0")
    tree.add_connection("druid_c4_r0", "druid_c5_r0")
    tree.add_connection("druid_c4_r0", "druid_c5_r1")
    tree.add_connection("druid_c5_r0", "druid_c6_r0")
    tree.add_connection("druid_c5_r1", "druid_c6_r1")
    tree.add_connection("druid_c5_r2", "druid_c6_r2")
    return tree
