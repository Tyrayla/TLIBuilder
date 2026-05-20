# ── MANUAL COMPLETION REQUIRED ────────────────────────────────────────────────
# Add every stat that can appear on a passive node as an entry below.
# This is a curated subset of models/stat.py — not every stat belongs here
# (e.g. gear-only stats like ATTACK_SPEED_GEAR should be omitted).
# Each entry carries three increments used by the stat editor to auto-fill
# rank values when you select a stat:
#   micro_increment     → step per rank for MICRO nodes (×1, ×2, ×3)
#   medium_increment    → step per rank for MEDIUM nodes (×1, ×2, ×3)
#   legendary_increment → single value for LEGENDARY_MEDIUM nodes (×1 only)
# Actual per-node values are stored in data/node_stats.json.
# ──────────────────────────────────────────────────────────────────────────────
from models.stat import Stat
from models.node_modifier_def import NodeModifierDef


NODE_MODIFIER_POOL: dict[Stat, NodeModifierDef] = {

    # ── Attributes ────────────────────────────────────────────────────────────
    Stat.STRENGTH:     NodeModifierDef(Stat.STRENGTH,      5.0,  10.0, 15.0),
    Stat.DEXTERITY:    NodeModifierDef(Stat.DEXTERITY,     5.0,  10.0, 15.0),
    Stat.INTELLIGENCE: NodeModifierDef(Stat.INTELLIGENCE,  5.0,  10.0, 15.0),

    # ── Baseline / Generic ────────────────────────────────────────────────────
    Stat.ARMOR_PEN:           NodeModifierDef(Stat.ARMOR_PEN,           0.05, 0.10, 0.15, "%"),
    Stat.DOUBLE_DMG_CHANCE:   NodeModifierDef(Stat.DOUBLE_DMG_CHANCE,   0.05, 0.10, 0.15, "%"),
    Stat.DMG_INC:             NodeModifierDef(Stat.DMG_INC,             0.09, 0.18, 0.15, "%"),
    Stat.DMG_ADDITIONAL:      NodeModifierDef(Stat.DMG_ADDITIONAL,      0.04, 0.08, 0.10, "%"),
    Stat.ALL_SKILL_LEVEL:     NodeModifierDef(Stat.ALL_SKILL_LEVEL,     1.0,  1.0,  2.0),
    Stat.ACTIVE_SKILL_LEVEL:  NodeModifierDef(Stat.ACTIVE_SKILL_LEVEL,  1.0,  1.0,  2.0),
    Stat.SUPPORT_SKILL_LEVEL: NodeModifierDef(Stat.SUPPORT_SKILL_LEVEL, 1.0,  1.0,  2.0),

    # ── Attack ────────────────────────────────────────────────────────────────
    Stat.ATTACK_DMG_INC:           NodeModifierDef(Stat.ATTACK_DMG_INC,           0.09, 0.18, 0.15, "%"),
    Stat.ATTACK_DMG_ADDITIONAL:    NodeModifierDef(Stat.ATTACK_DMG_ADDITIONAL,    0.04, 0.08, 0.10, "%"),
    Stat.ATTACK_DOUBLE_DMG_CHANCE: NodeModifierDef(Stat.ATTACK_DOUBLE_DMG_CHANCE, 0.05, 0.10, 0.15, "%"),
    Stat.ATTACK_SKILL_LEVEL:       NodeModifierDef(Stat.ATTACK_SKILL_LEVEL,       1.0,  1.0,  2.0),

    # ── Spell ─────────────────────────────────────────────────────────────────
    Stat.SPELL_DMG_INC:           NodeModifierDef(Stat.SPELL_DMG_INC,           0.09, 0.18, 0.15, "%"),
    Stat.SPELL_DMG_ADDITIONAL:    NodeModifierDef(Stat.SPELL_DMG_ADDITIONAL,    0.04, 0.08, 0.10, "%"),
    Stat.SPELL_DOUBLE_DMG_CHANCE: NodeModifierDef(Stat.SPELL_DOUBLE_DMG_CHANCE, 0.05, 0.10, 0.15, "%"),
    Stat.SPELL_SKILL_LEVEL:       NodeModifierDef(Stat.SPELL_SKILL_LEVEL,       1.0,  1.0,  2.0),

    # ── Melee ─────────────────────────────────────────────────────────────────
    Stat.MELEE_DMG_INC:        NodeModifierDef(Stat.MELEE_DMG_INC,        0.09, 0.18, 0.15, "%"),
    Stat.MELEE_DMG_ADDITIONAL: NodeModifierDef(Stat.MELEE_DMG_ADDITIONAL, 0.04, 0.08, 0.10, "%"),
    Stat.MELEE_SKILL_LEVEL:    NodeModifierDef(Stat.MELEE_SKILL_LEVEL,    1.0,  1.0,  2.0),

    # ── Area ──────────────────────────────────────────────────────────────────
    Stat.AREA_DMG_INC:        NodeModifierDef(Stat.AREA_DMG_INC,        0.09, 0.18, 0.15, "%"),
    Stat.AREA_DMG_ADDITIONAL: NodeModifierDef(Stat.AREA_DMG_ADDITIONAL, 0.04, 0.08, 0.10, "%"),

    # ── Projectile ────────────────────────────────────────────────────────────
    Stat.PROJECTILE_DMG_INC:        NodeModifierDef(Stat.PROJECTILE_DMG_INC,        0.09, 0.18, 0.15, "%"),
    Stat.PROJECTILE_DMG_ADDITIONAL: NodeModifierDef(Stat.PROJECTILE_DMG_ADDITIONAL, 0.04, 0.08, 0.10, "%"),
    Stat.PROJECTILE_SPEED_INC:      NodeModifierDef(Stat.PROJECTILE_SPEED_INC,      0.09, 0.18, 0.15, "%"),
    Stat.PROJECTILE_SKILL_LEVEL:    NodeModifierDef(Stat.PROJECTILE_SKILL_LEVEL,    1.0,  1.0,  2.0),

    # ── Minion ────────────────────────────────────────────────────────────────
    Stat.MINION_DMG_INC:           NodeModifierDef(Stat.MINION_DMG_INC,           0.09, 0.18, 0.15, "%"),
    Stat.MINION_DMG_ADDITIONAL:    NodeModifierDef(Stat.MINION_DMG_ADDITIONAL,    0.04, 0.08, 0.10, "%"),
    Stat.MINION_DOUBLE_DMG_CHANCE: NodeModifierDef(Stat.MINION_DOUBLE_DMG_CHANCE, 0.05, 0.10, 0.15, "%"),
    Stat.MINION_SKILL_LEVEL:       NodeModifierDef(Stat.MINION_SKILL_LEVEL,       1.0,  1.0,  2.0),
    Stat.SYNTH_DOUBLE_DMG_CHANCE:  NodeModifierDef(Stat.SYNTH_DOUBLE_DMG_CHANCE,  0.05, 0.10, 0.15, "%"),
    Stat.SYNTH_SKILL_LEVEL:        NodeModifierDef(Stat.SYNTH_SKILL_LEVEL,        1.0,  1.0,  2.0),

    # ── Sentry ────────────────────────────────────────────────────────────────
    Stat.SENTRY_DMG_ADDITIONAL:            NodeModifierDef(Stat.SENTRY_DMG_ADDITIONAL,            0.04, 0.08, 0.10, "%"),
    Stat.SENTRY_SKILL_CAST_FREQUENCY_INC:  NodeModifierDef(Stat.SENTRY_SKILL_CAST_FREQUENCY_INC,  0.09, 0.18, 0.15, "%"),

    # ── Physical ──────────────────────────────────────────────────────────────
    Stat.PHYSICAL_DMG_INC:        NodeModifierDef(Stat.PHYSICAL_DMG_INC,        0.09, 0.18, 0.15, "%"),
    Stat.PHYSICAL_DMG_ADDITIONAL: NodeModifierDef(Stat.PHYSICAL_DMG_ADDITIONAL, 0.04, 0.08, 0.10, "%"),
    Stat.PHYSICAL_AS_LIGHTNING:   NodeModifierDef(Stat.PHYSICAL_AS_LIGHTNING,   0.10, 0.20, 0.30, "%"),
    Stat.PHYSICAL_AS_COLD:        NodeModifierDef(Stat.PHYSICAL_AS_COLD,        0.10, 0.20, 0.30, "%"),
    Stat.PHYSICAL_AS_FIRE:        NodeModifierDef(Stat.PHYSICAL_AS_FIRE,        0.10, 0.20, 0.30, "%"),
    Stat.PHYSICAL_AS_EROSION:     NodeModifierDef(Stat.PHYSICAL_AS_EROSION,     0.10, 0.20, 0.30, "%"),
    Stat.PHYSICAL_SKILL_LEVEL:    NodeModifierDef(Stat.PHYSICAL_SKILL_LEVEL,    1.0,  1.0,  2.0),

    # ── Lightning ─────────────────────────────────────────────────────────────
    Stat.LIGHTNING_DMG_INC:            NodeModifierDef(Stat.LIGHTNING_DMG_INC,            0.09, 0.18, 0.15, "%"),
    Stat.LIGHTNING_DMG_ADDITIONAL:     NodeModifierDef(Stat.LIGHTNING_DMG_ADDITIONAL,     0.04, 0.08, 0.10, "%"),
    Stat.LIGHTNING_PEN:                NodeModifierDef(Stat.LIGHTNING_PEN,                0.05, 0.10, 0.15, "%"),
    Stat.LIGHTNING_ATTACK_DMG_FLAT_MIN:NodeModifierDef(Stat.LIGHTNING_ATTACK_DMG_FLAT_MIN,3.0,  6.0,  10.0),
    Stat.LIGHTNING_ATTACK_DMG_FLAT_MAX:NodeModifierDef(Stat.LIGHTNING_ATTACK_DMG_FLAT_MAX,5.0,  10.0, 15.0),
    Stat.LIGHTNING_SPELL_DMG_FLAT_MIN: NodeModifierDef(Stat.LIGHTNING_SPELL_DMG_FLAT_MIN, 3.0,  6.0,  10.0),
    Stat.LIGHTNING_SPELL_DMG_FLAT_MAX: NodeModifierDef(Stat.LIGHTNING_SPELL_DMG_FLAT_MAX, 5.0,  10.0, 15.0),
    Stat.LIGHTNING_SKILL_LEVEL:        NodeModifierDef(Stat.LIGHTNING_SKILL_LEVEL,        1.0,  1.0,  2.0),

    # ── Cold ──────────────────────────────────────────────────────────────────
    Stat.COLD_DMG_INC:            NodeModifierDef(Stat.COLD_DMG_INC,            0.09, 0.18, 0.15, "%"),
    Stat.COLD_DMG_ADDITIONAL:     NodeModifierDef(Stat.COLD_DMG_ADDITIONAL,     0.04, 0.08, 0.10, "%"),
    Stat.COLD_PEN:                NodeModifierDef(Stat.COLD_PEN,                0.05, 0.10, 0.15, "%"),
    Stat.COLD_ATTACK_DMG_FLAT_MIN:NodeModifierDef(Stat.COLD_ATTACK_DMG_FLAT_MIN,3.0,  6.0,  10.0),
    Stat.COLD_ATTACK_DMG_FLAT_MAX:NodeModifierDef(Stat.COLD_ATTACK_DMG_FLAT_MAX,5.0,  10.0, 15.0),
    Stat.COLD_SPELL_DMG_FLAT_MIN: NodeModifierDef(Stat.COLD_SPELL_DMG_FLAT_MIN, 3.0,  6.0,  10.0),
    Stat.COLD_SPELL_DMG_FLAT_MAX: NodeModifierDef(Stat.COLD_SPELL_DMG_FLAT_MAX, 5.0,  10.0, 15.0),
    Stat.COLD_SKILL_LEVEL:        NodeModifierDef(Stat.COLD_SKILL_LEVEL,        1.0,  1.0,  2.0),

    # ── Fire ──────────────────────────────────────────────────────────────────
    Stat.FIRE_DMG_INC:            NodeModifierDef(Stat.FIRE_DMG_INC,            0.09, 0.18, 0.15, "%"),
    Stat.FIRE_DMG_ADDITIONAL:     NodeModifierDef(Stat.FIRE_DMG_ADDITIONAL,     0.04, 0.08, 0.10, "%"),
    Stat.FIRE_PEN:                NodeModifierDef(Stat.FIRE_PEN,                0.05, 0.10, 0.15, "%"),
    Stat.FIRE_ATTACK_DMG_FLAT_MIN:NodeModifierDef(Stat.FIRE_ATTACK_DMG_FLAT_MIN,3.0,  6.0,  10.0),
    Stat.FIRE_ATTACK_DMG_FLAT_MAX:NodeModifierDef(Stat.FIRE_ATTACK_DMG_FLAT_MAX,5.0,  10.0, 15.0),
    Stat.FIRE_SPELL_DMG_FLAT_MIN: NodeModifierDef(Stat.FIRE_SPELL_DMG_FLAT_MIN, 3.0,  6.0,  10.0),
    Stat.FIRE_SPELL_DMG_FLAT_MAX: NodeModifierDef(Stat.FIRE_SPELL_DMG_FLAT_MAX, 5.0,  10.0, 15.0),
    Stat.FIRE_SKILL_LEVEL:        NodeModifierDef(Stat.FIRE_SKILL_LEVEL,        1.0,  1.0,  2.0),

    # ── Erosion ───────────────────────────────────────────────────────────────
    Stat.EROSION_DMG_INC:            NodeModifierDef(Stat.EROSION_DMG_INC,            0.09, 0.18, 0.15, "%"),
    Stat.EROSION_DMG_ADDITIONAL:     NodeModifierDef(Stat.EROSION_DMG_ADDITIONAL,     0.04, 0.08, 0.10, "%"),
    Stat.EROSION_PEN:                NodeModifierDef(Stat.EROSION_PEN,                0.05, 0.10, 0.15, "%"),
    Stat.EROSION_ATTACK_DMG_FLAT_MIN:NodeModifierDef(Stat.EROSION_ATTACK_DMG_FLAT_MIN,3.0,  6.0,  10.0),
    Stat.EROSION_ATTACK_DMG_FLAT_MAX:NodeModifierDef(Stat.EROSION_ATTACK_DMG_FLAT_MAX,5.0,  10.0, 15.0),
    Stat.EROSION_SPELL_DMG_FLAT_MIN: NodeModifierDef(Stat.EROSION_SPELL_DMG_FLAT_MIN, 3.0,  6.0,  10.0),
    Stat.EROSION_SPELL_DMG_FLAT_MAX: NodeModifierDef(Stat.EROSION_SPELL_DMG_FLAT_MAX, 5.0,  10.0, 15.0),
    Stat.EROSION_SKILL_LEVEL:        NodeModifierDef(Stat.EROSION_SKILL_LEVEL,        1.0,  1.0,  2.0),

    # ── Elemental ─────────────────────────────────────────────────────────────
    Stat.ELEMENTAL_DMG_INC:        NodeModifierDef(Stat.ELEMENTAL_DMG_INC,        0.09, 0.18, 0.15, "%"),
    Stat.ELEMENTAL_DMG_ADDITIONAL: NodeModifierDef(Stat.ELEMENTAL_DMG_ADDITIONAL, 0.04, 0.08, 0.10, "%"),
    Stat.ELEMENTAL_PEN:            NodeModifierDef(Stat.ELEMENTAL_PEN,            0.05, 0.10, 0.15, "%"),

    # ── Steep Strike ──────────────────────────────────────────────────────────
    Stat.STEEP_STRIKE_CHANCE:         NodeModifierDef(Stat.STEEP_STRIKE_CHANCE,         0.05, 0.10, 0.15, "%"),
    Stat.STEEP_STRIKE_ADDITIONAL_DMG: NodeModifierDef(Stat.STEEP_STRIKE_ADDITIONAL_DMG, 0.04, 0.08, 0.10, "%"),
    Stat.SWEEP_SLASH_ADDITIONAL_DMG:  NodeModifierDef(Stat.SWEEP_SLASH_ADDITIONAL_DMG,  0.04, 0.08, 0.10, "%"),

    # ── Cast Speed ────────────────────────────────────────────────────────────
    Stat.CAST_SPEED_INC:        NodeModifierDef(Stat.CAST_SPEED_INC,        0.03, 0.06, 0.08, "%"),
    Stat.CAST_SPEED_ADDITIONAL: NodeModifierDef(Stat.CAST_SPEED_ADDITIONAL, 0.02, 0.04, 0.06, "%"),

    # ── Attack Speed ──────────────────────────────────────────────────────────
    Stat.ATTACK_SPEED_INC:        NodeModifierDef(Stat.ATTACK_SPEED_INC,        0.03, 0.06, 0.08, "%"),
    Stat.ATTACK_SPEED_ADDITIONAL: NodeModifierDef(Stat.ATTACK_SPEED_ADDITIONAL, 0.02, 0.04, 0.06, "%"),

    # ── Critical Strike ───────────────────────────────────────────────────────
    Stat.ATTACK_CRIT_RATING_INC:       NodeModifierDef(Stat.ATTACK_CRIT_RATING_INC,       0.09, 0.18, 0.15, "%"),
    Stat.SPELL_CRIT_RATING_INC:        NodeModifierDef(Stat.SPELL_CRIT_RATING_INC,        0.09, 0.18, 0.15, "%"),
    Stat.MINION_CRIT_RATING_INC:       NodeModifierDef(Stat.MINION_CRIT_RATING_INC,       0.09, 0.18, 0.15, "%"),
    Stat.ATTACK_CRIT_RATING_FLAT:      NodeModifierDef(Stat.ATTACK_CRIT_RATING_FLAT,      10.0, 20.0, 30.0),
    Stat.SPELL_CRIT_RATING_FLAT:       NodeModifierDef(Stat.SPELL_CRIT_RATING_FLAT,       10.0, 20.0, 30.0),
    Stat.MINION_CRIT_RATING_FLAT:      NodeModifierDef(Stat.MINION_CRIT_RATING_FLAT,      10.0, 20.0, 30.0),
    Stat.SPIRIT_MAGI_CRIT_RATING_FLAT: NodeModifierDef(Stat.SPIRIT_MAGI_CRIT_RATING_FLAT, 10.0, 20.0, 30.0),
    Stat.CRIT_DMG:                     NodeModifierDef(Stat.CRIT_DMG,                     0.05, 0.10, 0.15, "%"),
    Stat.ATTACK_CRIT_DMG:              NodeModifierDef(Stat.ATTACK_CRIT_DMG,              0.05, 0.10, 0.15, "%"),
    Stat.SPELL_CRIT_DMG:               NodeModifierDef(Stat.SPELL_CRIT_DMG,               0.05, 0.10, 0.15, "%"),
    Stat.MINION_CRIT_DMG:              NodeModifierDef(Stat.MINION_CRIT_DMG,              0.05, 0.10, 0.15, "%"),
    Stat.PHYS_CRIT_DMG:                NodeModifierDef(Stat.PHYS_CRIT_DMG,                0.05, 0.10, 0.15, "%"),
    Stat.LIGHTNING_CRIT_DMG:           NodeModifierDef(Stat.LIGHTNING_CRIT_DMG,           0.05, 0.10, 0.15, "%"),
    Stat.COLD_CRIT_DMG:                NodeModifierDef(Stat.COLD_CRIT_DMG,                0.05, 0.10, 0.15, "%"),
    Stat.FIRE_CRIT_DMG:                NodeModifierDef(Stat.FIRE_CRIT_DMG,                0.05, 0.10, 0.15, "%"),
    Stat.EROSION_CRIT_DMG:             NodeModifierDef(Stat.EROSION_CRIT_DMG,             0.05, 0.10, 0.15, "%"),

    # ── Defense ───────────────────────────────────────────────────────────────
    Stat.ARMOR_FLAT:           NodeModifierDef(Stat.ARMOR_FLAT,           10.0, 20.0, 30.0),
    Stat.ELEMENTAL_RESISTANCE: NodeModifierDef(Stat.ELEMENTAL_RESISTANCE,  5.0, 10.0, 15.0),
    Stat.FIRE_RESISTANCE:      NodeModifierDef(Stat.FIRE_RESISTANCE,       5.0, 10.0, 15.0),
    Stat.COLD_RESISTANCE:      NodeModifierDef(Stat.COLD_RESISTANCE,       5.0, 10.0, 15.0),
    Stat.LIGHTNING_RESISTANCE: NodeModifierDef(Stat.LIGHTNING_RESISTANCE,  5.0, 10.0, 15.0),
    Stat.EROSION_RESISTANCE:   NodeModifierDef(Stat.EROSION_RESISTANCE,    5.0, 10.0, 15.0),

    # ── Blessings ─────────────────────────────────────────────────────────────
    Stat.TENACITY_BLESSING: NodeModifierDef(Stat.TENACITY_BLESSING, 1.0, 1.0, 1.0),
    Stat.AGILITY_BLESSING:  NodeModifierDef(Stat.AGILITY_BLESSING,  1.0, 1.0, 1.0),
    Stat.FOCUS_BLESSING:    NodeModifierDef(Stat.FOCUS_BLESSING,    1.0, 1.0, 1.0),
}
