from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType
from models.core_talent import CoreTalent, CoreTalentSlot


def build_tree() -> PassiveTree:
    tree = PassiveTree("God of Might")

    # Column 0 (label: 0)
    tree.add_node(PassiveNode(id="might_c0_r2", node_type=NodeType.MICRO, column=0, row=2, max_points=3))

    # Column 1 (label: 3)
    tree.add_node(PassiveNode(id="might_c1_r1", node_type=NodeType.MICRO,  column=1, row=1, max_points=3))
    tree.add_node(PassiveNode(id="might_c1_r2", node_type=NodeType.MEDIUM, column=1, row=2, max_points=3))
    tree.add_node(PassiveNode(id="might_c1_r3", node_type=NodeType.MICRO,  column=1, row=3, max_points=3))

    # Column 2 (label: 6)
    tree.add_node(PassiveNode(id="might_c2_r0", node_type=NodeType.MICRO,  column=2, row=0, max_points=3))
    tree.add_node(PassiveNode(id="might_c2_r1", node_type=NodeType.MEDIUM,  column=2, row=1, max_points=3))
    tree.add_node(PassiveNode(id="might_c2_r2", node_type=NodeType.MICRO, column=2, row=2, max_points=3))
    tree.add_node(PassiveNode(id="might_c2_r3", node_type=NodeType.MEDIUM,  column=2, row=3, max_points=3))
    tree.add_node(PassiveNode(id="might_c2_r4", node_type=NodeType.MICRO,  column=2, row=4, max_points=3))

    # Column 3 (label: 9) — no row 1
    tree.add_node(PassiveNode(id="might_c3_r0", node_type=NodeType.MEDIUM, column=3, row=0, max_points=3))
    tree.add_node(PassiveNode(id="might_c3_r2", node_type=NodeType.MEDIUM, column=3, row=2, max_points=3))
    tree.add_node(PassiveNode(id="might_c3_r3", node_type=NodeType.MICRO,  column=3, row=3, max_points=3))
    tree.add_node(PassiveNode(id="might_c3_r4", node_type=NodeType.MEDIUM,  column=3, row=4, max_points=3))

    # Column 4 (label: 12)
    tree.add_node(PassiveNode(id="might_c4_r0", node_type=NodeType.MICRO,  column=4, row=0, max_points=3))
    tree.add_node(PassiveNode(id="might_c4_r1", node_type=NodeType.MICRO,  column=4, row=1, max_points=3))
    tree.add_node(PassiveNode(id="might_c4_r2", node_type=NodeType.MICRO, column=4, row=2, max_points=3))
    tree.add_node(PassiveNode(id="might_c4_r3", node_type=NodeType.MEDIUM,  column=4, row=3, max_points=3))
    tree.add_node(PassiveNode(id="might_c4_r4", node_type=NodeType.MICRO,  column=4, row=4, max_points=3))

    # Column 5 (label: 15)
    tree.add_node(PassiveNode(id="might_c5_r0", node_type=NodeType.MEDIUM,  column=5, row=0, max_points=3))
    tree.add_node(PassiveNode(id="might_c5_r1", node_type=NodeType.MEDIUM,  column=5, row=1, max_points=3))
    tree.add_node(PassiveNode(id="might_c5_r2", node_type=NodeType.LEGENDARY_MEDIUM, column=5, row=2, max_points=1))
    tree.add_node(PassiveNode(id="might_c5_r3", node_type=NodeType.MICRO,  column=5, row=3, max_points=3))
    tree.add_node(PassiveNode(id="might_c5_r4", node_type=NodeType.MEDIUM,  column=5, row=4, max_points=3))

    # Column 6 (label: 18) — rows 0, 3, 4 only
    tree.add_node(PassiveNode(id="might_c6_r0", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=0, max_points=1))
    tree.add_node(PassiveNode(id="might_c6_r3", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=3, max_points=1))
    tree.add_node(PassiveNode(id="might_c6_r4", node_type=NodeType.LEGENDARY_MEDIUM, column=6, row=4, max_points=1))

    # ── Connections ────────────────────────────────────────────────────────────
    # Add connections manually once you have confirmed the tree layout:
    # tree.add_connection("might_cX_rY", "might_cX_rY")
    tree.add_connection("might_c1_r1", "might_c2_r1")
    tree.add_connection("might_c1_r3", "might_c2_r3")
    tree.add_connection("might_c2_r0", "might_c3_r0")
    tree.add_connection("might_c2_r2", "might_c3_r2")
    tree.add_connection("might_c2_r4", "might_c3_r4")
    tree.add_connection("might_c3_r3", "might_c4_r3")
    tree.add_connection("might_c4_r0", "might_c5_r0")
    tree.add_connection("might_c4_r1", "might_c5_r1")
    tree.add_connection("might_c4_r2", "might_c5_r2")
    tree.add_connection("might_c4_r4", "might_c5_r4")
    tree.add_connection("might_c5_r0", "might_c6_r0")
    tree.add_connection("might_c5_r3", "might_c6_r3")
    tree.add_connection("might_c5_r4", "might_c6_r4")


    # ── Core Talents ──────────────────────────────────────────────────────────
    tree.add_core_talent_slot(CoreTalentSlot(
        threshold=12,
        options=[
            CoreTalent(id="might_ct12_1", name="Might 1"),
            CoreTalent(id="might_ct12_2", name="Might 2"),
            CoreTalent(id="might_ct12_3", name="Might 3"),
        ],
    ))
    tree.add_core_talent_slot(CoreTalentSlot(
        threshold=24,
        options=[
            CoreTalent(id="might_ct24_1", name="Might 1"),
            CoreTalent(id="might_ct24_2", name="Might 2"),
            CoreTalent(id="might_ct24_3", name="Might 3"),
        ],
    ))
    tree.add_connection("might_c0_r2", "might_c1_r2")
    return tree
