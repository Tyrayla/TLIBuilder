from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType


def build_tree() -> PassiveTree:
    tree = PassiveTree("Goddess of Deception")

    # Column 0 (label: 0) — row 2 only
    tree.add_node(PassiveNode(id="deception_c0_r2", node_type=NodeType.MICRO, column=0, row=2, max_points=3))

    # Column 1 (label: 3)
    tree.add_node(PassiveNode(id="deception_c1_r1", node_type=NodeType.MICRO,  column=1, row=1, max_points=3))
    tree.add_node(PassiveNode(id="deception_c1_r2", node_type=NodeType.MEDIUM, column=1, row=2, max_points=3))
    tree.add_node(PassiveNode(id="deception_c1_r3", node_type=NodeType.MICRO,  column=1, row=3, max_points=3))

    # Column 2 (label: 6)
    tree.add_node(PassiveNode(id="deception_c2_r0", node_type=NodeType.MICRO,            column=2, row=0, max_points=3))
    tree.add_node(PassiveNode(id="deception_c2_r1", node_type=NodeType.MEDIUM, column=2, row=1, max_points=3))
    tree.add_node(PassiveNode(id="deception_c2_r2", node_type=NodeType.MICRO,            column=2, row=2, max_points=3))
    tree.add_node(PassiveNode(id="deception_c2_r3", node_type=NodeType.MEDIUM,            column=2, row=3, max_points=3))
    tree.add_node(PassiveNode(id="deception_c2_r4", node_type=NodeType.MICRO,            column=2, row=4, max_points=3))

    # Column 3 (label: 9)
    tree.add_node(PassiveNode(id="deception_c3_r0", node_type=NodeType.LEGENDARY_MEDIUM,  column=3, row=0, max_points=1))
    tree.add_node(PassiveNode(id="deception_c3_r1", node_type=NodeType.MICRO,  column=3, row=1, max_points=3))
    tree.add_node(PassiveNode(id="deception_c3_r2", node_type=NodeType.MEDIUM, column=3, row=2, max_points=3))
    tree.add_node(PassiveNode(id="deception_c3_r3", node_type=NodeType.MICRO,  column=3, row=3, max_points=3))
    tree.add_node(PassiveNode(id="deception_c3_r4", node_type=NodeType.MEDIUM,  column=3, row=4, max_points=3))

    # Column 4 (label: 12) — rows 0-3 only
    tree.add_node(PassiveNode(id="deception_c4_r0", node_type=NodeType.MICRO,  column=4, row=0, max_points=3))
    tree.add_node(PassiveNode(id="deception_c4_r1", node_type=NodeType.MEDIUM,  column=4, row=1, max_points=3))
    tree.add_node(PassiveNode(id="deception_c4_r2", node_type=NodeType.MICRO, column=4, row=2, max_points=3))
    tree.add_node(PassiveNode(id="deception_c4_r3", node_type=NodeType.LEGENDARY_MEDIUM,  column=4, row=3, max_points=1))

    # Column 5 (label: 15)
    tree.add_node(PassiveNode(id="deception_c5_r0", node_type=NodeType.MEDIUM,  column=5, row=0, max_points=3))
    tree.add_node(PassiveNode(id="deception_c5_r1", node_type=NodeType.MICRO,  column=5, row=1, max_points=3))
    tree.add_node(PassiveNode(id="deception_c5_r2", node_type=NodeType.MEDIUM, column=5, row=2, max_points=3))
    tree.add_node(PassiveNode(id="deception_c5_r3", node_type=NodeType.MICRO,  column=5, row=3, max_points=3))
    tree.add_node(PassiveNode(id="deception_c5_r4", node_type=NodeType.MICRO,  column=5, row=4, max_points=3))

    # Column 6 (label: 18) — no row 2
    tree.add_node(PassiveNode(id="deception_c6_r0", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=0, max_points=1))
    tree.add_node(PassiveNode(id="deception_c6_r1", node_type=NodeType.MEDIUM, column=6, row=1, max_points=3))
    tree.add_node(PassiveNode(id="deception_c6_r3", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=3, max_points=1))
    tree.add_node(PassiveNode(id="deception_c6_r4", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=4, max_points=1))

    # ── Connections ────────────────────────────────────────────────────────────
    # tree.add_connection("deception_cCOL_rROW", "deception_cCOL_rROW")

    tree.add_connection("deception_c0_r2", "deception_c1_r2")
    tree.add_connection("deception_c1_r1", "deception_c2_r1")
    tree.add_connection("deception_c1_r3", "deception_c2_r3")
    tree.add_connection("deception_c2_r2", "deception_c3_r2")
    tree.add_connection("deception_c3_r3", "deception_c4_r3")
    tree.add_connection("deception_c2_r4", "deception_c3_r4")
    tree.add_connection("deception_c2_r0", "deception_c3_r0")
    tree.add_connection("deception_c3_r1", "deception_c4_r1")
    tree.add_connection("deception_c4_r0", "deception_c5_r0")
    tree.add_connection("deception_c5_r0", "deception_c6_r0")
    tree.add_connection("deception_c5_r1", "deception_c6_r1")
    tree.add_connection("deception_c4_r2", "deception_c5_r2")
    tree.add_connection("deception_c5_r3", "deception_c6_r3")
    tree.add_connection("deception_c5_r4", "deception_c6_r4")
    return tree
