from __future__ import annotations
from dataclasses import dataclass
from models.stat import Stat


@dataclass(frozen=True)
class StatMeta:
    display_name:    str
    category:        str
    modifier_type:   str           # canonical type; see list at bottom of file
    unit:            str   = ""    # "" | "%"
    subgroup:        str   = ""    # granular grouping within category
    pipeline_stage:  str   = ""    # engine stage this feeds; see list at bottom
    tags:            tuple = ()    # skill/damage tags this applies to; () = universal
    affects:         tuple = ()    # damage forms: "hit" | "dot" | "secondary" | "reflect"
    stacking_rule:   str   = ""    # "additive" | "independent" | "additive_chance"
    ui_priority:     int   = 50    # 1-100; lower = displayed first
    source_types:    tuple = ()    # where this stat can originate from


# ── Shared source-type tuples ──────────────────────────────────────────────────
_T  = ("talent_node", "core_talent", "slate")
_TB = ("talent_node", "core_talent", "slate", "legendary_gear", "normal_gear")
_G  = ("legendary_gear", "normal_gear")

# ── Common affects tuples ──────────────────────────────────────────────────────
_HIT      = ("hit",)
_HIT_DOT  = ("hit", "dot")
_ALL_DMGF = ("hit", "dot", "secondary", "reflect")


STAT_META: dict[Stat, StatMeta] = {

    # ── Derived (final computed values — flat × (1 + inc%) × add pools) ───────
    Stat.STRENGTH: StatMeta(
        "Strength", "Attributes", "derived",
        subgroup="attribute", ui_priority=4, stacking_rule="additive",
    ),
    Stat.DEXTERITY: StatMeta(
        "Dexterity", "Attributes", "derived",
        subgroup="attribute", ui_priority=4, stacking_rule="additive",
    ),
    Stat.INTELLIGENCE: StatMeta(
        "Intelligence", "Attributes", "derived",
        subgroup="attribute", ui_priority=4, stacking_rule="additive",
    ),
    Stat.MAX_LIFE: StatMeta(
        "Maximum Life", "Life", "derived",
        subgroup="life", ui_priority=4, stacking_rule="additive",
    ),
    Stat.MAX_MANA: StatMeta(
        "Maximum Mana", "Mana", "derived",
        subgroup="mana", ui_priority=4, stacking_rule="additive",
    ),
    Stat.MAX_ENERGY_SHIELD: StatMeta(
        "Maximum Energy Shield", "Defence", "derived",
        subgroup="energy_shield", ui_priority=4, stacking_rule="additive",
    ),
    Stat.ARMOR: StatMeta(
        "Armor", "Defence", "derived",
        subgroup="defense", ui_priority=4, stacking_rule="additive",
    ),
    Stat.EVASION: StatMeta(
        "Evasion", "Defence", "derived",
        subgroup="defense", ui_priority=4, stacking_rule="additive",
    ),

    # ── Attributes ────────────────────────────────────────────────────────────
    Stat.STRENGTH_FLAT: StatMeta(
        "Strength", "Attributes", "base_stat",
        subgroup="attribute",     pipeline_stage="attribute",
        affects=_HIT_DOT,         stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.STRENGTH_INC: StatMeta(
        "Strength", "Attributes", "increased", "%",
        subgroup="attribute",     stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.DEXTERITY_FLAT: StatMeta(
        "Dexterity", "Attributes", "base_stat",
        subgroup="attribute",     pipeline_stage="attribute",
        affects=_HIT_DOT,         stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.DEXTERITY_INC: StatMeta(
        "Dexterity", "Attributes", "increased", "%",
        subgroup="attribute",     stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.INTELLIGENCE_FLAT: StatMeta(
        "Intelligence", "Attributes", "base_stat",
        subgroup="attribute",     pipeline_stage="attribute",
        affects=_HIT_DOT,         stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.INTELLIGENCE_INC: StatMeta(
        "Intelligence", "Attributes", "increased", "%",
        subgroup="attribute",     stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.ALL_STATS_FLAT: StatMeta(
        "to All Stats", "Attributes", "added_flat",
        subgroup="attribute",     stacking_rule="additive",
        ui_priority=6,            source_types=_TB,
    ),
    Stat.ALL_STATS_INC: StatMeta(
        "All Stats", "Attributes", "increased", "%",
        subgroup="attribute",     stacking_rule="additive",
        ui_priority=7,            source_types=_TB,
    ),

    # ── Generic ───────────────────────────────────────────────────────────────
    Stat.ARMOR_PEN: StatMeta(
        "Armor DMG Mitigation Penetration", "Generic", "penetration", "%",
        subgroup="mitigation",    pipeline_stage="mitigation",
        tags=("physical",),       affects=_ALL_DMGF,
        stacking_rule="additive", ui_priority=25,
        source_types=_T,
    ),
    Stat.DOUBLE_DMG_CHANCE: StatMeta(
        "Double Damage Chance", "Generic", "chance", "%",
        subgroup="double_damage",     pipeline_stage="double_damage",
        affects=_HIT,                 stacking_rule="additive_chance",
        ui_priority=20,               source_types=_T,
    ),
    Stat.DMG_INC: StatMeta(
        "Damage", "Generic", "increased", "%",
        subgroup="generic_damage",    pipeline_stage="increased_reduced",
        affects=_HIT_DOT,             stacking_rule="additive",
        ui_priority=1,                source_types=_T,
    ),
    Stat.DMG_ADDITIONAL: StatMeta(
        "Additional Damage", "Generic", "additional", "%",
        subgroup="generic_damage",    pipeline_stage="additional",
        affects=_HIT_DOT,             stacking_rule="additive",
        ui_priority=2,                source_types=_T,
    ),
    Stat.POST_MOBILITY_DMG_ADDITIONAL: StatMeta(
        "Additional Damage after Using Mobility Skills", "Generic", "additional", "%",
        subgroup="generic_damage",    pipeline_stage="additional",
        affects=_HIT_DOT,             stacking_rule="additive",
        ui_priority=4,                source_types=_T,
    ),
    Stat.DMG_MAX_ADDITIONAL: StatMeta(
        "Additional Max Damage", "Generic", "additional", "%",
        subgroup="generic_damage",    pipeline_stage="additional",
        affects=_HIT_DOT,             stacking_rule="additive",
        ui_priority=3,                source_types=_T,
    ),
    Stat.DMG_AVOID_CHANCE: StatMeta(
        "Chance to Avoid Damage", "Generic", "chance", "%",
        subgroup="generic_damage",    stacking_rule="additive_chance",
        ui_priority=25,               source_types=_T,
    ),
    Stat.BEAM_LENGTH_ADDITIONAL: StatMeta(
        "Additional Beam Length", "Generic", "added_flat",
        subgroup="mechanics",         stacking_rule="additive",
        ui_priority=70,               source_types=_T,
    ),
    Stat.ALL_SKILL_LEVEL: StatMeta(
        "All Skills' Levels", "Generic", "skill_level",
        subgroup="skill_level",       pipeline_stage="skill_level",
        affects=_HIT_DOT,             stacking_rule="additive",
        ui_priority=15,               source_types=_T,
    ),
    Stat.ACTIVE_SKILL_LEVEL: StatMeta(
        "Active Skill Level", "Generic", "skill_level",
        subgroup="skill_level",       pipeline_stage="skill_level",
        tags=("active",),             affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=16,
        source_types=_T,
    ),
    Stat.SUPPORT_SKILL_LEVEL: StatMeta(
        "Support Skill Level", "Generic", "skill_level",
        subgroup="skill_level",       pipeline_stage="skill_level",
        tags=("support",),            affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=17,
        source_types=_T,
    ),
    Stat.ALL_RESISTANCE_REDUCTION: StatMeta(
        "Enemy All Elemental Resistance", "Generic", "penetration", "%",
        subgroup="mitigation",        pipeline_stage="mitigation",
        affects=_ALL_DMGF,            stacking_rule="additive",
        ui_priority=26,               source_types=_T,
    ),
    Stat.ENEMY_NEARBY_DMG_TAKEN_ADDITIONAL: StatMeta(
        "Additional Damage Taken by Nearby Enemies", "Generic", "additional", "%",
        subgroup="generic_damage",    pipeline_stage="additional",
        affects=_HIT_DOT,             stacking_rule="additive",
        ui_priority=4,                source_types=_T,
    ),

    # ── Attack ────────────────────────────────────────────────────────────────
    Stat.ATTACK_DMG_INC: StatMeta(
        "Attack Damage", "Attack", "increased", "%",
        subgroup="attack_damage",     pipeline_stage="increased_reduced",
        tags=("attack",),             affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.ATTACK_DMG_ADDITIONAL: StatMeta(
        "Additional Attack Damage", "Attack", "additional", "%",
        subgroup="attack_damage",     pipeline_stage="additional",
        tags=("attack",),             affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.ATTACK_DOUBLE_DMG_CHANCE: StatMeta(
        "Attack Double Damage Chance", "Attack", "chance", "%",
        subgroup="double_damage",     pipeline_stage="double_damage",
        tags=("attack",),             affects=_HIT,
        stacking_rule="additive_chance", ui_priority=21,
        source_types=_T,
    ),
    Stat.ATTACK_SKILL_LEVEL: StatMeta(
        "Attack Skill Level", "Attack", "skill_level",
        subgroup="skill_level",       pipeline_stage="skill_level",
        tags=("attack",),             affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=15,
        source_types=_T,
    ),
    Stat.TWO_HANDED_BASE_DMG_ADDITIONAL: StatMeta(
        "Additional Two-Handed Base Damage", "Attack", "additional", "%",
        subgroup="attack_damage",     pipeline_stage="additional",
        tags=("attack", "two_handed"), affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=11,
        source_types=_T,
    ),
    Stat.SHIELD_DMG_INC: StatMeta(
        "Shield Damage", "Attack", "increased", "%",
        subgroup="attack_damage",     pipeline_stage="increased_reduced",
        tags=("attack",),             affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=11,
        source_types=_T,
    ),
    # ── Spell ─────────────────────────────────────────────────────────────────
    Stat.SPELL_DMG_INC: StatMeta(
        "Spell Damage", "Spell", "increased", "%",
        subgroup="spell_damage",      pipeline_stage="increased_reduced",
        tags=("spell",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.SPELL_DMG_ADDITIONAL: StatMeta(
        "Additional Spell Damage", "Spell", "additional", "%",
        subgroup="spell_damage",      pipeline_stage="additional",
        tags=("spell",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.SPELL_DOUBLE_DMG_CHANCE: StatMeta(
        "Spell Double Damage Chance", "Spell", "chance", "%",
        subgroup="double_damage",     pipeline_stage="double_damage",
        tags=("spell",),              affects=_HIT,
        stacking_rule="additive_chance", ui_priority=21,
        source_types=_T,
    ),
    Stat.SPELL_SKILL_LEVEL: StatMeta(
        "Spell Skill Level", "Spell", "skill_level",
        subgroup="skill_level",       pipeline_stage="skill_level",
        tags=("spell",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=15,
        source_types=_T,
    ),
    Stat.SPELL_BURST_CHARGE_SPEED_INC: StatMeta(
        "Spell Burst Charge Speed", "Spell", "increased", "%",
        subgroup="speed",             stacking_rule="additive",
        ui_priority=62,               source_types=_TB,
    ),
    Stat.LOW_MANA_SPELL_DMG_INC: StatMeta(
        "Spell Damage at Low Mana", "Spell", "increased", "%",
        subgroup="spell_damage",      pipeline_stage="increased_reduced",
        tags=("spell",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=14,
        source_types=_T,
    ),

    # ── Melee ─────────────────────────────────────────────────────────────────
    Stat.MELEE_DMG_INC: StatMeta(
        "Melee Damage", "Melee", "increased", "%",
        subgroup="melee_damage",      pipeline_stage="increased_reduced",
        tags=("melee",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.MELEE_DMG_ADDITIONAL: StatMeta(
        "Additional Melee Damage", "Melee", "additional", "%",
        subgroup="melee_damage",      pipeline_stage="additional",
        tags=("melee",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.MELEE_SKILL_LEVEL: StatMeta(
        "Melee Skill Level", "Melee", "skill_level",
        subgroup="skill_level",       pipeline_stage="skill_level",
        tags=("melee",),              affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=15,
        source_types=_T,
    ),

    # ── Area ──────────────────────────────────────────────────────────────────
    Stat.AREA_DMG_INC: StatMeta(
        "Area Damage", "Area", "increased", "%",
        subgroup="area_damage",       pipeline_stage="increased_reduced",
        tags=("area",),               affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),
    Stat.AREA_DMG_ADDITIONAL: StatMeta(
        "Additional Area Damage", "Area", "additional", "%",
        subgroup="area_damage",       pipeline_stage="additional",
        tags=("area",),               affects=_HIT_DOT,
        stacking_rule="additive",     ui_priority=10,
        source_types=_T,
    ),

    # ── Projectile ────────────────────────────────────────────────────────────
    Stat.PROJECTILE_DMG_INC: StatMeta(
        "Projectile Damage", "Projectile", "increased", "%",
        subgroup="projectile_damage",  pipeline_stage="increased_reduced",
        tags=("projectile",),          affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.PROJECTILE_DMG_ADDITIONAL: StatMeta(
        "Additional Projectile Damage", "Projectile", "additional", "%",
        subgroup="projectile_damage",   pipeline_stage="additional",
        tags=("projectile",),           affects=_HIT_DOT,
        stacking_rule="additive",       ui_priority=10,
        source_types=_T,
    ),
    Stat.PROJECTILE_SPEED_INC: StatMeta(
        "Projectile Speed", "Projectile", "increased", "%",
        subgroup="speed",              tags=("projectile",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),
    Stat.PROJECTILE_SKILL_LEVEL: StatMeta(
        "Projectile Skill Level", "Projectile", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("projectile",),          affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.PROJECTILE_CRIT_DMG_INC: StatMeta(
        "Projectile Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("projectile",),          affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.PROJECTILE_CRIT_RATING_INC: StatMeta(
        "Projectile Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("projectile",),          affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.PROJECTILE_QUANTITY_FLAT: StatMeta(
        "Projectile Quantity", "Projectile", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.PARABOLIC_PROJECTILE_SPLITS_FLAT: StatMeta(
        "Parabolic Projectile Split Quantity", "Projectile", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),
    Stat.HORIZONTAL_PROJECTILE_PENETRATION_FLAT: StatMeta(
        "Horizontal Projectile Penetration", "Projectile", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=71,                source_types=_TB,
    ),

    # ── Minion ────────────────────────────────────────────────────────────────
    Stat.MINION_DMG_INC: StatMeta(
        "Minion Damage", "Minion", "increased", "%",
        subgroup="minion_damage",      pipeline_stage="increased_reduced",
        tags=("minion",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_DMG_ADDITIONAL: StatMeta(
        "Additional Minion Damage", "Minion", "additional", "%",
        subgroup="minion_damage",      pipeline_stage="additional",
        tags=("minion",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_DMG_MAX: StatMeta(
        "Additional Max Damage for Minions", "Minion", "additional", "%",
        subgroup="minion_damage",      pipeline_stage="additional",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.MINION_DOUBLE_DMG_CHANCE: StatMeta(
        "Minion Double Damage Chance", "Minion", "chance", "%",
        subgroup="double_damage",      pipeline_stage="double_damage",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive_chance", ui_priority=21,
        source_types=_T,
    ),
    Stat.MINION_SKILL_LEVEL: StatMeta(
        "Minion Skill Level", "Minion", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("minion",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.MINION_FIRE_DMG_INC: StatMeta(
        "Minion Fire Damage", "Minion", "increased", "%",
        subgroup="minion_damage",      pipeline_stage="increased_reduced",
        tags=("minion", "fire"),       affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_FIRE_PEN_INC: StatMeta(
        "Minion Fire Penetration", "Minion", "penetration", "%",
        subgroup="minion_penetration",  pipeline_stage="penetration",
        tags=("minion", "fire"),        affects=_HIT_DOT,
        stacking_rule="additive",       ui_priority=9,
        source_types=_T,
    ),
    Stat.MINION_COLD_DMG_INC: StatMeta(
        "Minion Cold Damage", "Minion", "increased", "%",
        subgroup="minion_damage",      pipeline_stage="increased_reduced",
        tags=("minion", "cold"),       affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_LIGHTNING_DMG_INC: StatMeta(
        "Minion Lightning Damage", "Minion", "increased", "%",
        subgroup="minion_damage",      pipeline_stage="increased_reduced",
        tags=("minion", "lightning"),  affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_EROSION_DMG_INC: StatMeta(
        "Minion Erosion Damage", "Minion", "increased", "%",
        subgroup="minion_damage",      pipeline_stage="increased_reduced",
        tags=("minion", "erosion"),    affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_PHYSICAL_DMG_INC: StatMeta(
        "Physical Damage for Minions", "Minion", "increased", "%",
        subgroup="minion_damage",      pipeline_stage="increased_reduced",
        tags=("minion", "physical"),   affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.MINION_MAX_LIFE_INC: StatMeta(
        "Minion Max Life", "Minion", "increased", "%",
        subgroup="minion_life",        stacking_rule="additive",
        ui_priority=31,                source_types=_T,
    ),
    Stat.MINION_ATTACK_SPEED_INC: StatMeta(
        "Minion Attack Speed", "Minion", "increased", "%",
        subgroup="speed",              tags=("minion",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),
    Stat.MINION_CAST_SPEED_INC: StatMeta(
        "Minion Cast Speed", "Minion", "increased", "%",
        subgroup="speed",              tags=("minion",),
        stacking_rule="additive",      ui_priority=61,
        source_types=_T,
    ),
    Stat.MINION_LIFE_REGEN_SPEED_INC: StatMeta(
        "Minion Life Regeneration Speed", "Minion", "increased", "%",
        subgroup="minion_life",        stacking_rule="additive",
        ui_priority=33,                source_types=_T,
    ),
    Stat.MINION_MULTISTRIKE_CHANCE: StatMeta(
        "Minion Multistrike Chance", "Minion", "chance", "%",
        subgroup="minion_mechanics",   stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.MINION_SKILL_AREA_INC: StatMeta(
        "Minion Skill Area", "Minion", "increased", "%",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=30,                source_types=_T,
    ),
    Stat.MINION_DAMAGING_AILMENT_CHANCE: StatMeta(
        "Chance for Minions to Inflict Damaging Ailments", "Minion", "chance", "%",
        subgroup="minion_mechanics",   stacking_rule="additive_chance",
        ui_priority=23,                source_types=_T,
    ),
    Stat.MINION_TRAUMA_CHANCE: StatMeta(
        "Chance for Minions to Inflict Trauma", "Minion", "chance", "%",
        subgroup="minion_mechanics",   stacking_rule="additive_chance",
        ui_priority=24,                source_types=_T,
    ),
    Stat.MINION_IGNITE_CHANCE: StatMeta(
        "Ignite Chance for Minions", "Ailments", "chance", "%",
        subgroup="ignite",             stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.MINION_AFFLICTION_EFFECT_INC: StatMeta(
        "Minion Affliction Effect", "Ailments", "increased", "%",
        subgroup="affliction",         stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),
    Stat.MINION_AFFLICTION_PER_SECOND_FLAT: StatMeta(
        "Affliction by Minions per second", "Ailments", "added_flat",
        subgroup="affliction",         stacking_rule="additive",
        ui_priority=72,                source_types=_T,
    ),
    Stat.MINION_ARMOR_PEN: StatMeta(
        "Armor DMG Mitigation Penetration for Minions", "Minion", "penetration", "%",
        subgroup="minion_damage",      pipeline_stage="penetration",
        tags=("minion",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=25,
        source_types=_T,
    ),
    Stat.MINION_DURATION_INC: StatMeta(
        "Minion Duration", "Minion", "increased", "%",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.MINION_PHYSIQUE_INC: StatMeta(
        "Physique for Minions", "Minion", "increased", "%",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=71,                source_types=_TB,
    ),
    Stat.MINION_LIFE_REGAIN_INC: StatMeta(
        "Life Regain for Minions", "Minion", "increased", "%",
        subgroup="minion_life",        stacking_rule="additive",
        ui_priority=34,                source_types=_TB,
    ),

    # Synthetic Troops
    Stat.SYNTH_DOUBLE_DMG_CHANCE: StatMeta(
        "Chance for Synthetic Troop Minions to Deal Double Damage", "Minion", "chance", "%",
        subgroup="double_damage",      pipeline_stage="double_damage",
        tags=("synth",),               affects=_HIT,
        stacking_rule="additive_chance", ui_priority=22,
        source_types=_T,
    ),
    Stat.SYNTH_SKILL_LEVEL: StatMeta(
        "Synthetic Troop Skill Level", "Minion", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("synth",),               affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=16,
        source_types=_T,
    ),
    Stat.MAX_SYNTH_TROOPS_FLAT: StatMeta(
        "Max Summonable Synthetic Troops", "Minion", "added_flat",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.SYNTH_TROOP_DMG_TAKEN_ADDITIONAL: StatMeta(
        "Synthetic Troop Additional Damage Taken", "Minion", "additional", "%",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=73,                source_types=_T,
    ),
    Stat.COMMAND_PER_SECOND_FLAT: StatMeta(
        "Command per second", "Minion", "added_flat",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=71,                source_types=_TB,
    ),
    Stat.MAX_COMMAND_FLAT: StatMeta(
        "Max Command", "Minion", "added_flat",
        subgroup="minion_mechanics",   stacking_rule="additive",
        ui_priority=72,                source_types=_TB,
    ),

    # ── Sentry ────────────────────────────────────────────────────────────────
    Stat.SENTRY_DMG_INC: StatMeta(
        "Sentry Damage", "Sentry", "increased", "%",
        subgroup="sentry_damage",      pipeline_stage="increased",
        tags=("sentry",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.SENTRY_DMG_ADDITIONAL: StatMeta(
        "Additional Sentry Damage", "Sentry", "additional", "%",
        subgroup="sentry_damage",      pipeline_stage="additional",
        tags=("sentry",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.SENTRY_SKILL_CAST_FREQUENCY_INC: StatMeta(
        "Sentry Cast Frequency", "Sentry", "increased", "%",
        subgroup="speed",              tags=("sentry",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),
    Stat.SENTRY_SKILL_CAST_FREQUENCY_ADDITIONAL: StatMeta(
        "Additional Sentry Cast Frequency", "Sentry", "additional", "%",
        subgroup="speed",              tags=("sentry",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),
    Stat.SENTRY_CRIT_DMG_INC: StatMeta(
        "Sentry Skill Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("sentry",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.SENTRY_CRIT_RATING_INC: StatMeta(
        "Sentry Skill Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("sentry",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.MAX_SENTRY_QUANTITY_FLAT: StatMeta(
        "Sentry Quantity that can be Deployed at a Time", "Sentry", "added_flat",
        subgroup="sentry_mechanics",   stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.SENTRY_DURATION_INC: StatMeta(
        "Sentry Duration", "Sentry", "increased", "%",
        subgroup="sentry_mechanics",   stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),
    Stat.SENTRY_SKILL_AREA_INC: StatMeta(
        "Sentry Skill Area", "Sentry", "increased", "%",
        subgroup="sentry_mechanics",   stacking_rule="additive",
        ui_priority=72,                source_types=_T,
    ),
    Stat.SENTRY_START_TIME_ADDITIONAL: StatMeta(
        "Sentry Start Time", "Sentry", "added_flat",
        subgroup="sentry_mechanics",   stacking_rule="additive",
        ui_priority=73,                source_types=_T,
    ),
    Stat.SENTRY_PROJECTILE_SPEED_INC: StatMeta(
        "Sentry Projectile Speed", "Sentry", "increased", "%",
        subgroup="sentry_mechanics",   stacking_rule="additive",
        ui_priority=74,                source_types=_T,
    ),

    # ── Spirit Magi ───────────────────────────────────────────────────────────
    Stat.SPIRIT_MAGI_DMG_INC: StatMeta(
        "Spirit Magus Skill Damage", "Spirit Magi", "increased", "%",
        subgroup="spirit_magi_damage", pipeline_stage="increased_reduced",
        tags=("spirit_magi",),         affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.SPIRIT_MAGI_DMG_ADDITIONAL: StatMeta(
        "Additional Spirit Magus Skill Damage", "Spirit Magi", "additional", "%",
        subgroup="spirit_magi_damage", pipeline_stage="additional",
        tags=("spirit_magi",),         affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.SPIRIT_MAGI_ULTIMATE_DMG_INC: StatMeta(
        "Spirit Magus Ultimate Damage and Ailment Damage", "Spirit Magi", "increased", "%",
        subgroup="spirit_magi_damage", pipeline_stage="increased_reduced",
        tags=("spirit_magi",),         affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.SPIRIT_MAGI_ORIGIN_EFFECT_INC: StatMeta(
        "Origin of Spirit Magus effect", "Spirit Magi", "increased", "%",
        subgroup="spirit_magi_damage", stacking_rule="additive",
        ui_priority=11,                source_types=_T,
    ),
    Stat.SPIRIT_MAGI_SKILL_LEVEL: StatMeta(
        "Spirit Magus Skill Level", "Spirit Magi", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("spirit_magi",),         affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.SPIRIT_MAGI_CRIT_RATING_FLAT: StatMeta(
        "Spirit Magi Critical Strike Rating (Flat)", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("spirit_magi",),         affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_TB,
    ),
    Stat.SPIRIT_MAGI_ENHANCED_SKILL_CHANCE: StatMeta(
        "Chance for Spirit Magi to Use an Enhanced Skill", "Spirit Magi", "chance", "%",
        subgroup="spirit_magi_mechanics", stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.SPIRIT_MAGI_CDR_SPEED_INC: StatMeta(
        "Spirit Magus Ultimate Cooldown Recovery Speed", "Spirit Magi", "increased", "%",
        subgroup="spirit_magi_mechanics", stacking_rule="additive",
        ui_priority=30,                source_types=_T,
    ),
    Stat.SPIRIT_MAGI_DMG_TAKEN_ADDITIONAL: StatMeta(
        "Additional Damage Taken by Spirit Magi", "Spirit Magi", "additional", "%",
        subgroup="spirit_magi_mechanics", stacking_rule="additive",
        ui_priority=50,                source_types=_T,
    ),
    Stat.MAX_SPIRIT_MAGI_FLAT: StatMeta(
        "Max Spirit Magi in Map", "Spirit Magi", "added_flat",
        subgroup="spirit_magi_mechanics", stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),

    # ── Physical ──────────────────────────────────────────────────────────────
    Stat.PHYSICAL_DMG_INC: StatMeta(
        "Physical Damage", "Physical", "increased", "%",
        subgroup="physical_damage",    pipeline_stage="increased_reduced",
        tags=("physical",),            affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.PHYSICAL_DMG_ADDITIONAL: StatMeta(
        "Additional Physical Damage", "Physical", "additional", "%",
        subgroup="physical_damage",    pipeline_stage="additional",
        tags=("physical",),            affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.PHYSICAL_AS_LIGHTNING: StatMeta(
        "Physical as Lightning", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "lightning"),
        ui_priority=80,                source_types=_TB,
    ),
    Stat.PHYSICAL_AS_COLD: StatMeta(
        "Physical as Cold", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "cold"),
        ui_priority=80,                source_types=_TB,
    ),
    Stat.PHYSICAL_AS_FIRE: StatMeta(
        "Physical as Fire", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "fire"),
        ui_priority=80,                source_types=_TB,
    ),
    Stat.PHYSICAL_AS_EROSION: StatMeta(
        "Physical as Erosion", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "erosion"),
        ui_priority=80,                source_types=_TB,
    ),
    Stat.PHYSICAL_AS_ELEMENTAL: StatMeta(
        "Physical as Fire Cold and Lightning Damage", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "elemental"),
        ui_priority=80,                source_types=_TB,
    ),
    Stat.PHYSICAL_SKILL_LEVEL: StatMeta(
        "Physical Skill Level", "Physical", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("physical",),            affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.PHYSICAL_ATTACK_DMG_FLAT_MIN: StatMeta(
        "Min Physical Attack Damage", "Physical", "added_flat",
        subgroup="physical_damage",    pipeline_stage="added_flat",
        tags=("physical", "attack"),   affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.PHYSICAL_ATTACK_DMG_FLAT_MAX: StatMeta(
        "Max Physical Attack Damage", "Physical", "added_flat",
        subgroup="physical_damage",    pipeline_stage="added_flat",
        tags=("physical", "attack"),   affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.PHYSICAL_SPELL_DMG_FLAT_MIN: StatMeta(
        "Min Physical Spell Damage", "Physical", "added_flat",
        subgroup="physical_damage",    pipeline_stage="added_flat",
        tags=("physical", "spell"),    affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.PHYSICAL_SPELL_DMG_FLAT_MAX: StatMeta(
        "Max Physical Spell Damage", "Physical", "added_flat",
        subgroup="physical_damage",    pipeline_stage="added_flat",
        tags=("physical", "spell"),    affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.PHYSICAL_DMG_REFLECTION: StatMeta(
        "Physical Damage Reflection", "Physical", "added_flat",
        subgroup="reflection",         stacking_rule="additive",
        ui_priority=75,                source_types=_TB,
    ),

    # ── Lightning ─────────────────────────────────────────────────────────────
    Stat.LIGHTNING_DMG_INC: StatMeta(
        "Lightning Damage", "Lightning", "increased", "%",
        subgroup="lightning_damage",   pipeline_stage="increased_reduced",
        tags=("lightning",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.LIGHTNING_DMG_ADDITIONAL: StatMeta(
        "Additional Lightning Damage", "Lightning", "additional", "%",
        subgroup="lightning_damage",   pipeline_stage="additional",
        tags=("lightning",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.LIGHTNING_PEN: StatMeta(
        "Lightning Penetration", "Lightning", "penetration", "%",
        subgroup="lightning_damage",   pipeline_stage="penetration",
        tags=("lightning",),           affects=_ALL_DMGF,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),
    Stat.LIGHTNING_ATTACK_DMG_FLAT_MIN: StatMeta(
        "Min Lightning Attack Damage", "Lightning", "added_flat",
        subgroup="lightning_damage",   pipeline_stage="added_flat",
        tags=("lightning", "attack"),  affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.LIGHTNING_ATTACK_DMG_FLAT_MAX: StatMeta(
        "Max Lightning Attack Damage", "Lightning", "added_flat",
        subgroup="lightning_damage",   pipeline_stage="added_flat",
        tags=("lightning", "attack"),  affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.LIGHTNING_SPELL_DMG_FLAT_MIN: StatMeta(
        "Min Lightning Spell Damage", "Lightning", "added_flat",
        subgroup="lightning_damage",   pipeline_stage="added_flat",
        tags=("lightning", "spell"),   affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.LIGHTNING_SPELL_DMG_FLAT_MAX: StatMeta(
        "Max Lightning Spell Damage", "Lightning", "added_flat",
        subgroup="lightning_damage",   pipeline_stage="added_flat",
        tags=("lightning", "spell"),   affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.LIGHTNING_SKILL_LEVEL: StatMeta(
        "Lightning Skill Level", "Lightning", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("lightning",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.LIGHTNING_DMG_REFLECTION: StatMeta(
        "Lightning Damage Reflection", "Lightning", "added_flat",
        subgroup="reflection",         stacking_rule="additive",
        ui_priority=75,                source_types=_TB,
    ),

    # ── Cold ──────────────────────────────────────────────────────────────────
    Stat.COLD_DMG_INC: StatMeta(
        "Cold Damage", "Cold", "increased", "%",
        subgroup="cold_damage",        pipeline_stage="increased_reduced",
        tags=("cold",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.COLD_DMG_ADDITIONAL: StatMeta(
        "Additional Cold Damage", "Cold", "additional", "%",
        subgroup="cold_damage",        pipeline_stage="additional",
        tags=("cold",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.COLD_PEN: StatMeta(
        "Cold Penetration", "Cold", "penetration", "%",
        subgroup="cold_damage",        pipeline_stage="penetration",
        tags=("cold",),                affects=_ALL_DMGF,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),
    Stat.COLD_ATTACK_DMG_FLAT_MIN: StatMeta(
        "Min Cold Attack Damage", "Cold", "added_flat",
        subgroup="cold_damage",        pipeline_stage="added_flat",
        tags=("cold", "attack"),       affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.COLD_ATTACK_DMG_FLAT_MAX: StatMeta(
        "Max Cold Attack Damage", "Cold", "added_flat",
        subgroup="cold_damage",        pipeline_stage="added_flat",
        tags=("cold", "attack"),       affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.COLD_SPELL_DMG_FLAT_MIN: StatMeta(
        "Min Cold Spell Damage", "Cold", "added_flat",
        subgroup="cold_damage",        pipeline_stage="added_flat",
        tags=("cold", "spell"),        affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.COLD_SPELL_DMG_FLAT_MAX: StatMeta(
        "Max Cold Spell Damage", "Cold", "added_flat",
        subgroup="cold_damage",        pipeline_stage="added_flat",
        tags=("cold", "spell"),        affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.COLD_SKILL_LEVEL: StatMeta(
        "Cold Skill Level", "Cold", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("cold",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.COLD_DMG_REFLECTION: StatMeta(
        "Cold Damage Reflection", "Cold", "added_flat",
        subgroup="reflection",         stacking_rule="additive",
        ui_priority=75,                source_types=_TB,
    ),

    # ── Fire ──────────────────────────────────────────────────────────────────
    Stat.FIRE_DMG_INC: StatMeta(
        "Fire Damage", "Fire", "increased", "%",
        subgroup="fire_damage",        pipeline_stage="increased_reduced",
        tags=("fire",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.FIRE_DMG_ADDITIONAL: StatMeta(
        "Additional Fire Damage", "Fire", "additional", "%",
        subgroup="fire_damage",        pipeline_stage="additional",
        tags=("fire",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.FIRE_PEN: StatMeta(
        "Fire Penetration", "Fire", "penetration", "%",
        subgroup="fire_damage",        pipeline_stage="penetration",
        tags=("fire",),                affects=_ALL_DMGF,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),
    Stat.FIRE_ATTACK_DMG_FLAT_MIN: StatMeta(
        "Min Fire Attack Damage", "Fire", "added_flat",
        subgroup="fire_damage",        pipeline_stage="added_flat",
        tags=("fire", "attack"),       affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.FIRE_ATTACK_DMG_FLAT_MAX: StatMeta(
        "Max Fire Attack Damage", "Fire", "added_flat",
        subgroup="fire_damage",        pipeline_stage="added_flat",
        tags=("fire", "attack"),       affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.FIRE_SPELL_DMG_FLAT_MIN: StatMeta(
        "Min Fire Spell Damage", "Fire", "added_flat",
        subgroup="fire_damage",        pipeline_stage="added_flat",
        tags=("fire", "spell"),        affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.FIRE_SPELL_DMG_FLAT_MAX: StatMeta(
        "Max Fire Spell Damage", "Fire", "added_flat",
        subgroup="fire_damage",        pipeline_stage="added_flat",
        tags=("fire", "spell"),        affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.FIRE_SKILL_LEVEL: StatMeta(
        "Fire Skill Level", "Fire", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("fire",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.FIRE_DOT_DMG_INC: StatMeta(
        "Fire Damage over Time", "Fire", "increased", "%",
        subgroup="fire_damage",        pipeline_stage="increased_reduced",
        tags=("fire", "dot"),          affects=("dot",),
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.FIRE_DMG_REFLECTION: StatMeta(
        "Fire Damage Reflection", "Fire", "added_flat",
        subgroup="reflection",         stacking_rule="additive",
        ui_priority=75,                source_types=_TB,
    ),

    # ── Erosion ───────────────────────────────────────────────────────────────
    Stat.EROSION_DMG_INC: StatMeta(
        "Erosion Damage", "Erosion", "increased", "%",
        subgroup="erosion_damage",     pipeline_stage="increased_reduced",
        tags=("erosion",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.EROSION_DMG_ADDITIONAL: StatMeta(
        "Additional Erosion Damage", "Erosion", "additional", "%",
        subgroup="erosion_damage",     pipeline_stage="additional",
        tags=("erosion",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.EROSION_PEN: StatMeta(
        "Erosion Penetration", "Erosion", "penetration", "%",
        subgroup="erosion_damage",     pipeline_stage="penetration",
        tags=("erosion",),             affects=_ALL_DMGF,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),
    Stat.EROSION_ATTACK_DMG_FLAT_MIN: StatMeta(
        "Min Erosion Attack Damage", "Erosion", "added_flat",
        subgroup="erosion_damage",     pipeline_stage="added_flat",
        tags=("erosion", "attack"),    affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.EROSION_ATTACK_DMG_FLAT_MAX: StatMeta(
        "Max Erosion Attack Damage", "Erosion", "added_flat",
        subgroup="erosion_damage",     pipeline_stage="added_flat",
        tags=("erosion", "attack"),    affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.EROSION_SPELL_DMG_FLAT_MIN: StatMeta(
        "Min Erosion Spell Damage", "Erosion", "added_flat",
        subgroup="erosion_damage",     pipeline_stage="added_flat",
        tags=("erosion", "spell"),     affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.EROSION_SPELL_DMG_FLAT_MAX: StatMeta(
        "Max Erosion Spell Damage", "Erosion", "added_flat",
        subgroup="erosion_damage",     pipeline_stage="added_flat",
        tags=("erosion", "spell"),     affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.EROSION_SKILL_LEVEL: StatMeta(
        "Erosion Skill Level", "Erosion", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("erosion",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),
    Stat.EROSION_DMG_REFLECTION: StatMeta(
        "Erosion Damage Reflection", "Erosion", "added_flat",
        subgroup="reflection",         stacking_rule="additive",
        ui_priority=75,                source_types=_TB,
    ),

    # ── Elemental ─────────────────────────────────────────────────────────────
    Stat.ELEMENTAL_DMG_INC: StatMeta(
        "Elemental Damage", "Elemental", "increased", "%",
        subgroup="elemental_damage",   pipeline_stage="increased_reduced",
        tags=("elemental",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.ELEMENTAL_DMG_ADDITIONAL: StatMeta(
        "Additional Elemental Damage", "Elemental", "additional", "%",
        subgroup="elemental_damage",   pipeline_stage="additional",
        tags=("elemental",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.ELEMENTAL_PEN: StatMeta(
        "Elemental Penetration", "Elemental", "penetration", "%",
        subgroup="elemental_damage",   pipeline_stage="penetration",
        tags=("elemental",),           affects=_ALL_DMGF,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),

    # ── Ailments — Generic ────────────────────────────────────────────────────
    Stat.AILMENT_DMG_INC: StatMeta(
        "Ailment Damage", "Ailments", "increased", "%",
        subgroup="ailment_damage",     pipeline_stage="increased_reduced",
        tags=("ailment",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_TB,
    ),
    Stat.AILMENT_DMG_FLAT_MIN: StatMeta(
        "Min Base Ailment Damage", "Ailments", "added_flat",
        subgroup="ailment_damage",     pipeline_stage="added_flat",
        tags=("ailment",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.AILMENT_DMG_FLAT_MAX: StatMeta(
        "Max Base Ailment Damage", "Ailments", "added_flat",
        subgroup="ailment_damage",     pipeline_stage="added_flat",
        tags=("ailment",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.DAMAGING_AILMENT_CHANCE: StatMeta(
        "Chance to Inflict Damaging Ailments", "Ailments", "chance", "%",
        subgroup="ailment_chance",     stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.ELEMENTAL_AILMENT_AVOID_CHANCE: StatMeta(
        "Chance to Avoid Elemental Ailments", "Ailments", "chance", "%",
        subgroup="ailment_chance",     stacking_rule="additive_chance",
        ui_priority=23,                source_types=_T,
    ),
    Stat.DOT_DMG_INC: StatMeta(
        "Damage Over Time", "Ailments", "increased", "%",
        subgroup="ailment_damage",     pipeline_stage="increased_reduced",
        tags=("dot",),                 affects=("dot",),
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),

    # ── Ignite ────────────────────────────────────────────────────────────────
    Stat.IGNITE_DMG_INC: StatMeta(
        "Ignite Damage", "Ailments", "increased", "%",
        subgroup="ignite",             pipeline_stage="increased_reduced",
        tags=("ignite",),              affects=("dot",),
        stacking_rule="additive",      ui_priority=10,
        source_types=_TB,
    ),
    Stat.IGNITE_DMG_FLAT_MIN: StatMeta(
        "Min Base Ignite Damage", "Ailments", "added_flat",
        subgroup="ignite",             pipeline_stage="added_flat",
        tags=("ignite",),              affects=("dot",),
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.IGNITE_DMG_FLAT_MAX: StatMeta(
        "Max Base Ignite Damage", "Ailments", "added_flat",
        subgroup="ignite",             pipeline_stage="added_flat",
        tags=("ignite",),              affects=("dot",),
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.IGNITE_CHANCE: StatMeta(
        "Chance to Ignite targets", "Ailments", "chance", "%",
        subgroup="ignite",             stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),

    # ── Wilt ──────────────────────────────────────────────────────────────────
    Stat.WILT_DMG_INC: StatMeta(
        "Wilt Damage", "Ailments", "increased", "%",
        subgroup="wilt",               pipeline_stage="increased_reduced",
        tags=("wilt",),                affects=("dot",),
        stacking_rule="additive",      ui_priority=10,
        source_types=_TB,
    ),
    Stat.WILT_DMG_FLAT_MIN: StatMeta(
        "Min Base Wilt Damage", "Ailments", "added_flat",
        subgroup="wilt",               pipeline_stage="added_flat",
        tags=("wilt",),                affects=("dot",),
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.WILT_DMG_FLAT_MAX: StatMeta(
        "Max Base Wilt Damage", "Ailments", "added_flat",
        subgroup="wilt",               pipeline_stage="added_flat",
        tags=("wilt",),                affects=("dot",),
        stacking_rule="additive",      ui_priority=40,
        source_types=_TB,
    ),
    Stat.WILT_CHANCE: StatMeta(
        "Wilt Chance", "Ailments", "chance", "%",
        subgroup="wilt",               stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.WILT_DURATION_INC: StatMeta(
        "Wilt Duration", "Ailments", "increased", "%",
        subgroup="wilt",               stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),

    # ── Tangle ────────────────────────────────────────────────────────────────
    Stat.TANGLE_DMG_INC: StatMeta(
        "Tangle Damage", "Ailments", "increased", "%",
        subgroup="tangle",             pipeline_stage="increased_reduced",
        tags=("tangle",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.TANGLE_DURATION_INC: StatMeta(
        "Tangle Duration", "Ailments", "increased", "%",
        subgroup="tangle",             stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.MAX_TANGLE_QUANTITY_FLAT: StatMeta(
        "Max Tangle Quantity", "Ailments", "added_flat",
        subgroup="tangle",             stacking_rule="additive",
        ui_priority=71,                source_types=_TB,
    ),

    # ── Trauma ────────────────────────────────────────────────────────────────
    Stat.TRAUMA_DMG_INC: StatMeta(
        "Trauma Damage", "Ailments", "increased", "%",
        subgroup="trauma",             pipeline_stage="increased_reduced",
        tags=("trauma",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.TRAUMA_CHANCE: StatMeta(
        "Chance to inflict Trauma", "Ailments", "chance", "%",
        subgroup="trauma",             stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.TRAUMA_DMG_ADDITIONAL_ON_CRIT: StatMeta(
        "Additional Trauma Damage Dealt by Critical Strikes", "Ailments", "additional", "%",
        subgroup="trauma",             pipeline_stage="additional",
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.TRAUMA_REAPING_DURATION_INC: StatMeta(
        "Trauma Reaping Duration", "Ailments", "increased", "%",
        subgroup="trauma",             stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),

    # ── Frostbite ─────────────────────────────────────────────────────────────
    Stat.FROSTBITE_EFFECT_INC: StatMeta(
        "Frostbite Effect", "Ailments", "increased", "%",
        subgroup="frostbite",          stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.MAX_FROSTBITE_RATING_FLAT: StatMeta(
        "Max Frostbite Rating", "Ailments", "added_flat",
        subgroup="frostbite",          stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),

    # ── Affliction ────────────────────────────────────────────────────────────
    Stat.AFFLICTION_EFFECT_INC: StatMeta(
        "Affliction Effect", "Ailments", "increased", "%",
        subgroup="affliction",         stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.AFFLICTION_PER_SECOND_FLAT: StatMeta(
        "Affliction per second", "Ailments", "added_flat",
        subgroup="affliction",         stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),

    # ── Deterioration ─────────────────────────────────────────────────────────
    Stat.DETERIORATION_CHANCE: StatMeta(
        "Deterioration Chance", "Ailments", "chance", "%",
        subgroup="deterioration",      stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.DETERIORATION_DMG_INC: StatMeta(
        "Deterioration Damage", "Ailments", "increased", "%",
        subgroup="deterioration",      stacking_rule="additive",
        ui_priority=10,                source_types=_T,
    ),
    Stat.DETERIORATION_DMG_ADDITIONAL: StatMeta(
        "Additional Deterioration Damage", "Ailments", "additional", "%",
        subgroup="deterioration",      stacking_rule="additive",
        ui_priority=10,                source_types=_T,
    ),
    Stat.DETERIORATION_DURATION_ADDITIONAL: StatMeta(
        "Additional Deterioration Duration", "Ailments", "additional", "%",
        subgroup="deterioration",      stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),

    # ── Status Effects ────────────────────────────────────────────────────────
    Stat.NUMBED_EFFECT_INC: StatMeta(
        "Numbed Effect", "Ailments", "increased", "%",
        subgroup="status_effects",     stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.NUMBED_THRESHOLD_INC: StatMeta(
        "to the Max Life and Energy Shield Thresholds for Inflicting Numbed", "Ailments", "increased", "%",
        subgroup="status_effects",     stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),
    Stat.SLOW_CHANCE: StatMeta(
        "Slow Chance", "Ailments", "chance", "%",
        subgroup="status_effects",     stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.SLOW_EFFECT_RECEIVED_INC: StatMeta(
        "Slow Effect received", "Ailments", "increased", "%",
        subgroup="status_effects",     stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.BLIND_CHANCE: StatMeta(
        "Blind Chance", "Ailments", "chance", "%",
        subgroup="status_effects",     stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.PARALYSIS_EFFECT_2H_INC: StatMeta(
        "Inflicted Paralysis Effect", "Ailments", "increased", "%",
        subgroup="status_effects",     stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),

    # ── Channeled / Triggered / Combo ─────────────────────────────────────────
    Stat.CHANNELED_DMG_INC: StatMeta(
        "Damage for Channeled Skills", "Generic", "increased", "%",
        subgroup="generic_damage",     pipeline_stage="increased_reduced",
        tags=("channeled",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.CHANNELED_ATTACK_SPEED_INC: StatMeta(
        "Channeled Attack Speed", "Attack Speed", "increased", "%",
        subgroup="speed",              tags=("channeled", "attack"),
        stacking_rule="additive",      ui_priority=59,
        source_types=_T,
    ),
    Stat.CHANNELED_CAST_SPEED_INC: StatMeta(
        "Channeled Cast Speed", "Cast Speed", "increased", "%",
        subgroup="speed",              tags=("channeled", "spell"),
        stacking_rule="additive",      ui_priority=59,
        source_types=_T,
    ),
    Stat.TRIGGERED_DMG_INC: StatMeta(
        "Damage for Triggered Skills", "Generic", "increased", "%",
        subgroup="generic_damage",     pipeline_stage="increased_reduced",
        tags=("triggered",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.COMBO_FINISHER_ADDITIONAL: StatMeta(
        "Combo Finisher Amplification", "Generic", "additional", "%",
        subgroup="generic_damage",     pipeline_stage="additional",
        tags=("combo_finisher",),      affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_TB,
    ),
    Stat.MULTISTRIKE_INCREASING_DMG_INC: StatMeta(
        "Multistrikes deal increasing damage", "Generic", "additional", "%",
        subgroup="generic_damage",     pipeline_stage="additional",
        tags=("multistrike",),         affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_TB,
    ),
    Stat.BARRAGE_DMG_PER_WAVE_INC: StatMeta(
        "Barrage Skills damage increase per wave", "Generic", "additional", "%",
        subgroup="generic_damage",     pipeline_stage="additional",
        tags=("barrage",),             affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_TB,
    ),
    Stat.MULTISTRIKE_CHANCE: StatMeta(
        "Chance to Multistrike", "Generic", "chance", "%",
        subgroup="mechanics",          stacking_rule="additive_chance",
        ui_priority=22,                source_types=_T,
    ),
    Stat.MAX_CHANNELED_STACKS_FLAT: StatMeta(
        "Max Channeled Stacks", "Generic", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=75,                source_types=_T,
    ),

    # ── Steep Strike ──────────────────────────────────────────────────────────
    Stat.STEEP_STRIKE_CHANCE: StatMeta(
        "Steep Strike Chance", "Steep Strike", "chance", "%",
        subgroup="steep_strike",       pipeline_stage="double_damage",
        stacking_rule="additive_chance", ui_priority=22,
        source_types=_T,
    ),
    Stat.STEEP_STRIKE_ADDITIONAL_DMG: StatMeta(
        "Steep Strike Additional Damage", "Steep Strike", "additional", "%",
        subgroup="steep_strike",       pipeline_stage="additional",
        affects=_HIT,                  stacking_rule="additive",
        ui_priority=12,                source_types=_T,
    ),
    Stat.SWEEP_SLASH_ADDITIONAL_DMG: StatMeta(
        "Sweep Slash Additional Damage", "Steep Strike", "additional", "%",
        subgroup="steep_strike",       pipeline_stage="additional",
        affects=_HIT,                  stacking_rule="additive",
        ui_priority=12,                source_types=_T,
    ),

    # ── Cast Speed ────────────────────────────────────────────────────────────
    Stat.CAST_SPEED_INC: StatMeta(
        "Cast Speed", "Cast Speed", "increased", "%",
        subgroup="speed",              tags=("spell",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),
    Stat.CAST_SPEED_ADDITIONAL: StatMeta(
        "Additional Cast Speed", "Cast Speed", "additional", "%",
        subgroup="speed",              tags=("spell",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),

    # ── Attack Speed ──────────────────────────────────────────────────────────
    Stat.ATTACK_SPEED_GEAR: StatMeta(
        "Attack Speed (Gear)", "Attack Speed", "added_flat", "%",
        subgroup="speed",              tags=("attack",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_G,
    ),
    Stat.ATTACK_SPEED_MH: StatMeta(
        "Attack Speed (Main Hand)", "Attack Speed", "added_flat", "%",
        subgroup="speed",              tags=("attack",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_G,
    ),
    Stat.ATTACK_SPEED_INC: StatMeta(
        "Attack Speed", "Attack Speed", "increased", "%",
        subgroup="speed",              tags=("attack",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),
    Stat.ATTACK_SPEED_ADDITIONAL: StatMeta(
        "Additional Attack Speed", "Attack Speed", "additional", "%",
        subgroup="speed",              tags=("attack",),
        stacking_rule="additive",      ui_priority=60,
        source_types=_T,
    ),

    # ── Other Speeds ──────────────────────────────────────────────────────────
    Stat.MOVEMENT_SPEED_INC: StatMeta(
        "Movement Speed", "Utility", "increased", "%",
        subgroup="speed",              stacking_rule="additive",
        ui_priority=61,                source_types=_T,
    ),
    Stat.FOCUS_SPEED_INC: StatMeta(
        "Focus Speed", "Utility", "increased", "%",
        subgroup="speed",              stacking_rule="additive",
        ui_priority=62,                source_types=_TB,
    ),

    # ── Critical Strike — Rating ──────────────────────────────────────────────
    Stat.ATTACK_CRIT_RATING_GEAR: StatMeta(
        "Attack Critical Strike Rating for this Gear", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_G,
    ),
    Stat.ATTACK_CRIT_RATING_MH: StatMeta(
        "Critical Strike Rating for the Main-Hand Weapon", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_G,
    ),
    Stat.CRIT_RATING_INC: StatMeta(
        "Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        affects=_HIT,                  stacking_rule="additive",
        ui_priority=10,                source_types=_T,
    ),
    Stat.ATTACK_CRIT_RATING_INC: StatMeta(
        "Attack Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.SPELL_CRIT_RATING_INC: StatMeta(
        "Spell Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("spell",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.MINION_CRIT_RATING_INC: StatMeta(
        "Minion Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.ATTACK_CRIT_RATING_FLAT: StatMeta(
        "Attack Critical Strike Rating", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_TB,
    ),
    Stat.WEAPON_CRIT_RATING_FLAT: StatMeta(
        "Critical Strike Rating (Weapon)", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_G,
    ),
    Stat.SPELL_CRIT_RATING_FLAT: StatMeta(
        "Spell Critical Strike Rating", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("spell",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_TB,
    ),
    Stat.MINION_CRIT_RATING_FLAT: StatMeta(
        "Minion Critical Strike Rating", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_TB,
    ),
    Stat.SPIRIT_MAGI_CRIT_RATING_FLAT: StatMeta(
        "Spirit Magi Critical Strike Rating (Flat)", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("spirit_magi",),         affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_TB,
    ),
    Stat.PROJECTILE_CRIT_RATING_INC: StatMeta(
        "Projectile Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("projectile",),          affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.SENTRY_CRIT_RATING_INC: StatMeta(
        "Sentry Skill Critical Strike Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("sentry",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),

    # ── Critical Strike — Damage ──────────────────────────────────────────────
    Stat.CRIT_DMG_INC: StatMeta(
        "Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        affects=_HIT,                  stacking_rule="additive",
        ui_priority=12,                source_types=_T,
    ),
    Stat.ATTACK_CRIT_DMG_INC: StatMeta(
        "Attack Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.SPELL_CRIT_DMG_INC: StatMeta(
        "Spell Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("spell",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.MINION_CRIT_DMG_INC: StatMeta(
        "Minion Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.PHYSICAL_CRIT_DMG_INC: StatMeta(
        "Physical Skill Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("physical",),            affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.LIGHTNING_CRIT_DMG_INC: StatMeta(
        "Lightning Skill Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("lightning",),           affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.COLD_CRIT_DMG_INC: StatMeta(
        "Cold Skill Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("cold",),                affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.FIRE_CRIT_DMG_INC: StatMeta(
        "Fire Skill Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("fire",),                affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.EROSION_CRIT_DMG_INC: StatMeta(
        "Erosion Skill Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("erosion",),             affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),

    # ── Double Damage / Knockback ─────────────────────────────────────────────
    Stat.KNOCKBACK_CHANCE: StatMeta(
        "Knockback Chance", "Utility", "chance", "%",
        subgroup="mechanics",          stacking_rule="additive_chance",
        ui_priority=65,                source_types=_T,
    ),
    Stat.KNOCKBACK_DISTANCE_INC: StatMeta(
        "Knockback Distance", "Utility", "increased", "%",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=65,                source_types=_T,
    ),

    # ── Life ──────────────────────────────────────────────────────────────────
    Stat.MAX_LIFE_FLAT: StatMeta(
        "Max Life", "Life", "added_flat",
        subgroup="life",               stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.MAX_LIFE_INC: StatMeta(
        "Max Life", "Life", "increased", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=32,                source_types=_T,
    ),
    Stat.LIFE_REGEN_FLAT: StatMeta(
        "Life Regeneration", "Life", "added_flat",
        subgroup="life",               stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.LIFE_REGEN_INC: StatMeta(
        "Life Regeneration", "Life", "added_flat", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.LIFE_REGEN_SPEED_INC: StatMeta(
        "Life Regeneration Speed", "Life", "increased", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=35,                source_types=_T,
    ),
    Stat.LIFE_REGAIN_INC: StatMeta(
        "Life Regain", "Life", "increased", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=36,                source_types=_TB,
    ),
    Stat.LIFE_REGAIN_INTERVAL_ADDITIONAL: StatMeta(
        "Additional Life Regain Interval", "Life", "additional", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=37,                source_types=_T,
    ),
    Stat.REGAIN_INTERVAL_ADDITIONAL: StatMeta(
        "Additional Regain Interval", "Life", "additional", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=38,                source_types=_T,
    ),
    Stat.LIFE_ON_SKILL_USE_FLAT: StatMeta(
        "Life on Skill Use", "Life", "added_flat",
        subgroup="life",               stacking_rule="additive",
        ui_priority=38,                source_types=_TB,
    ),
    Stat.LIFE_ON_DEFEAT_PCT: StatMeta(
        "Life on Defeat", "Life", "added_flat", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=39,                source_types=_TB,
    ),
    Stat.INJURY_BUFFER_INC: StatMeta(
        "Injury Buffer", "Life", "increased", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=40,                source_types=_TB,
    ),

    # ── Mana ──────────────────────────────────────────────────────────────────
    Stat.MAX_MANA_FLAT: StatMeta(
        "Max Mana", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.MAX_MANA_INC: StatMeta(
        "Max Mana", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=32,                source_types=_T,
    ),
    Stat.MANA_REGEN_FLAT: StatMeta(
        "Mana Regeneration", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.MANA_REGEN_INC: StatMeta(
        "Mana Regeneration Speed", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.MANA_REGEN_PCT: StatMeta(
        "Mana Regeneration", "Mana", "added_flat", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=35,                source_types=_TB,
    ),
    Stat.MANA_BEFORE_LIFE_INC: StatMeta(
        "Mana Before Life", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=36,                source_types=_TB,
    ),
    Stat.SKILL_COST_FLAT: StatMeta(
        "Skill Cost", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=37,                source_types=_TB,
    ),
    Stat.ATTACK_SKILL_COST_FLAT: StatMeta(
        "Attack Skill Cost", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=37,                source_types=_TB,
    ),
    Stat.SPELL_SKILL_COST_FLAT: StatMeta(
        "Spell Skill Cost", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=38,                source_types=_TB,
    ),
    Stat.SKILL_COST_INC: StatMeta(
        "Skill Cost", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=38,                source_types=_TB,
    ),
    Stat.SKILL_COST_REDUCTION: StatMeta(
        "Skill Cost Reduction", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=39,                source_types=_T,
    ),
    Stat.SEALED_MANA_COMPENSATION_INC: StatMeta(
        "Sealed Mana Compensation", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=40,                source_types=_TB,
    ),

    # ── Energy Shield ─────────────────────────────────────────────────────────
    Stat.MAX_ENERGY_SHIELD_FLAT: StatMeta(
        "Max Energy Shield", "Energy Shield", "added_flat",
        subgroup="energy_shield",      stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.MAX_ENERGY_SHIELD_INC: StatMeta(
        "Max Energy Shield", "Energy Shield", "increased", "%",
        subgroup="energy_shield",      stacking_rule="additive",
        ui_priority=32,                source_types=_TB,
    ),
    Stat.ENERGY_SHIELD_REGAIN_INC: StatMeta(
        "Energy Shield Regain", "Energy Shield", "increased", "%",
        subgroup="energy_shield",      stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.ENERGY_SHIELD_CHARGE_SPEED_INC: StatMeta(
        "Energy Shield Charge Speed", "Energy Shield", "increased", "%",
        subgroup="energy_shield",      stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.ENERGY_SHIELD_REGAIN_INTERVAL_ADDITIONAL: StatMeta(
        "Energy Shield Regain Interval", "Energy Shield", "added_flat",
        subgroup="energy_shield",      stacking_rule="additive",
        ui_priority=35,                source_types=_T,
    ),
    Stat.ENERGY_SHIELD_CHARGE_INTERVAL_ADDITIONAL: StatMeta(
        "Energy Shield Charge Interval", "Energy Shield", "added_flat",
        subgroup="energy_shield",      stacking_rule="additive",
        ui_priority=36,                source_types=_T,
    ),

    # ── Barrier ───────────────────────────────────────────────────────────────
    Stat.BARRIER_ABSORPTION_RATE_INC: StatMeta(
        "Barrier Absorption Rate", "Defense", "increased", "%",
        subgroup="barrier",            stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.BARRIER_SHIELD_INC: StatMeta(
        "Barrier Shield", "Defense", "increased", "%",
        subgroup="barrier",            stacking_rule="additive",
        ui_priority=35,                source_types=_TB,
    ),

    # ── Defense ───────────────────────────────────────────────────────────────
    Stat.ARMOR_FLAT: StatMeta(
        "Armor", "Defense", "added_flat",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.ARMOR_INC: StatMeta(
        "Armor", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=31,                source_types=_T,
    ),
    Stat.EVASION_FLAT: StatMeta(
        "Evasion", "Defense", "added_flat",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=32,                source_types=_TB,
    ),
    Stat.EVASION_INC: StatMeta(
        "Evasion", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=33,                source_types=_T,
    ),
    Stat.EVASION_ON_SPELL_DMG_INC: StatMeta(
        "Additional Evasion on Spell Damage", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.DEFENSE_INC: StatMeta(
        "Defense", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=30,                source_types=_TB,
    ),
    Stat.SHIELD_DEFENSE_INC: StatMeta(
        "Defense from Shield", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.ELEMENTAL_RESISTANCE: StatMeta(
        "Elemental Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=35,                source_types=_TB,
    ),
    Stat.FIRE_RESISTANCE: StatMeta(
        "Fire Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=36,                source_types=_TB,
    ),
    Stat.COLD_RESISTANCE: StatMeta(
        "Cold Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=36,                source_types=_TB,
    ),
    Stat.LIGHTNING_RESISTANCE: StatMeta(
        "Lightning Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=36,                source_types=_TB,
    ),
    Stat.EROSION_RESISTANCE: StatMeta(
        "Erosion Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=36,                source_types=_TB,
    ),
    Stat.FIRE_RESISTANCE_MAX_INC: StatMeta(
        "Max Fire Resistance", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=37,                source_types=_T,
    ),
    Stat.COLD_RESISTANCE_MAX_INC: StatMeta(
        "Max Cold Resistance", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=37,                source_types=_T,
    ),
    Stat.LIGHTNING_RESISTANCE_MAX_INC: StatMeta(
        "Max Lightning Resistance", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=37,                source_types=_T,
    ),
    Stat.EROSION_RESISTANCE_MAX_INC: StatMeta(
        "Max Erosion Resistance", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=37,                source_types=_T,
    ),
    Stat.ATTACK_BLOCK_CHANCE_INC: StatMeta(
        "Attack Block Chance", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=38,                source_types=_T,
    ),
    Stat.SPELL_BLOCK_CHANCE_INC: StatMeta(
        "Spell Block Chance", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=38,                source_types=_T,
    ),
    Stat.BLOCK_RATIO_INC: StatMeta(
        "Block Ratio", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=39,                source_types=_T,
    ),
    Stat.INTIMIDATING_EFFECT_INC: StatMeta(
        "Intimidating Effect", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=40,                source_types=_TB,
    ),
    Stat.SHIELD_ENERGY_SHIELD_INC: StatMeta(
        "Energy Shield gained from Shield", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=41,                source_types=_T,
    ),
    Stat.CHEST_DEFENSE_INC: StatMeta(
        "Defense from Chest Armor", "Defense", "increased", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=42,                source_types=_T,
    ),

    # ── Damage Taken ──────────────────────────────────────────────────────────
    Stat.DMG_TAKEN_ADDITIONAL: StatMeta(
        "Additional Damage Taken", "Damage Taken", "additional", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=50,                source_types=_TB,
    ),
    Stat.PHYSICAL_DMG_TAKEN_ADDITIONAL: StatMeta(
        "Additional Physical Damage Taken", "Damage Taken", "additional", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=51,                source_types=_TB,
    ),
    Stat.ELEMENTAL_DMG_TAKEN_ADDITIONAL: StatMeta(
        "Additional Elemental Damage Taken", "Damage Taken", "additional", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=51,                source_types=_TB,
    ),
    Stat.TRAUMA_DMG_TAKEN_INC: StatMeta(
        "Trauma Damage Taken", "Damage Taken", "increased", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=52,                source_types=_TB,
    ),
    Stat.DOT_DMG_TAKEN_ADDITIONAL: StatMeta(
        "Additional Damage Over Time Taken", "Damage Taken", "additional", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=53,                source_types=_TB,
    ),

    # ── Damage Taken Conversion ────────────────────────────────────────────────
    Stat.COLD_TAKEN_AS_FIRE_INC: StatMeta(
        "Cold Damage taken as Fire", "Damage Taken", "conversion", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=60,                source_types=_TB,
    ),
    Stat.LIGHTNING_TAKEN_AS_FIRE_INC: StatMeta(
        "Lightning Damage taken as Fire", "Damage Taken", "conversion", "%",
        subgroup="damage_taken",       stacking_rule="additive",
        ui_priority=60,                source_types=_TB,
    ),

    # ── Cooldown Recovery ─────────────────────────────────────────────────────
    Stat.CDR_SPEED_INC: StatMeta(
        "Cooldown Recovery Speed", "Utility", "increased", "%",
        subgroup="utility",            stacking_rule="additive",
        ui_priority=62,                source_types=_T,
    ),
    Stat.WARCRY_CDR_SPEED_INC: StatMeta(
        "Warcry Cooldown Recovery Speed", "Utility", "increased", "%",
        subgroup="utility",            stacking_rule="additive",
        ui_priority=63,                source_types=_T,
    ),

    # ── Skill Mechanics ───────────────────────────────────────────────────────
    Stat.SKILL_AREA_INC: StatMeta(
        "Skill Area", "Utility", "increased", "%",
        subgroup="skill_mechanics",    stacking_rule="additive",
        ui_priority=64,                source_types=_TB,
    ),
    Stat.SKILL_EFFECT_DURATION_INC: StatMeta(
        "Skill Effect Duration", "Utility", "increased", "%",
        subgroup="skill_mechanics",    stacking_rule="additive",
        ui_priority=65,                source_types=_TB,
    ),
    Stat.RESTORATION_EFFECT_INC: StatMeta(
        "Restoration Effect", "Utility", "increased", "%",
        subgroup="skill_mechanics",    stacking_rule="additive",
        ui_priority=66,                source_types=_TB,
    ),

    # ── Reaping ───────────────────────────────────────────────────────────────
    Stat.REAPING_DURATION_INC: StatMeta(
        "Reaping Duration", "Utility", "increased", "%",
        subgroup="reaping",            stacking_rule="additive",
        ui_priority=67,                source_types=_TB,
    ),
    Stat.REAPING_RECOVERY_SPEED_INC: StatMeta(
        "Reaping Recovery Speed", "Utility", "increased", "%",
        subgroup="reaping",            stacking_rule="additive",
        ui_priority=68,                source_types=_TB,
    ),

    # ── Buff / Aura Effects ───────────────────────────────────────────────────
    Stat.FERVOR_EFFECT_INC: StatMeta(
        "Fervor Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.BLUR_EFFECT_INC: StatMeta(
        "Blur Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.WARCRY_EFFECT_INC: StatMeta(
        "Warcry Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.ELIXIR_EFFECT_INC: StatMeta(
        "Elixir Skill Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.AURA_EFFECT_INC: StatMeta(
        "Aura Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.CURSE_EFFECT_INC: StatMeta(
        "Curse Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.CURSE_SKILL_AREA_INC: StatMeta(
        "Curse Skill Area", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),
    Stat.MARK_EFFECT_INC: StatMeta(
        "Mark Effect", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.MARK_ON_CRIT_CHANCE: StatMeta(
        "Chance to Mark Enemy on Critical Strike", "Buffs", "chance", "%",
        subgroup="buff_effect",        stacking_rule="additive_chance",
        ui_priority=71,                source_types=_T,
    ),
    Stat.CC_EFFECT_INC: StatMeta(
        "Crowd Control Effects", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.ILL_OMEN_EFFICIENCY_INC: StatMeta(
        "Ill Omen Cumulative Efficiency", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=71,                source_types=_TB,
    ),
    Stat.DEMOLISHER_CHARGE_SPEED_INC: StatMeta(
        "Demolisher Charge Restoration Speed", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=72,                source_types=_T,
    ),
    Stat.AGILITY_BLESSING_DURATION_INC: StatMeta(
        "Agility Blessing Duration", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=73,                source_types=_T,
    ),
    Stat.FOCUS_BLESSING_DURATION_INC: StatMeta(
        "Focus Blessing Duration", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=74,                source_types=_T,
    ),
    Stat.TENACITY_BLESSING_DURATION_INC: StatMeta(
        "Tenacity Blessing Duration", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=75,                source_types=_T,
    ),
    Stat.BLESSING_DURATION_INC: StatMeta(
        "Blessing Duration", "Buffs", "increased", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=75,                source_types=_TB,
    ),
    Stat.FOCUS_DMG_ENHANCEMENT_ADDITIONAL: StatMeta(
        "Focus Damage Enhancement", "Buffs", "additional", "%",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=76,                source_types=_TB,
    ),
    Stat.AILMENT_DMG_ENHANCEMENT_ADDITIONAL: StatMeta(
        "Ailment Damage Enhancement", "Ailments", "additional", "%",
        subgroup="ailment",            stacking_rule="additive",
        ui_priority=76,                source_types=_TB,
    ),
    Stat.WARCRY_MIN_TARGETS_FLAT: StatMeta(
        "Minimum Enemies Affected by Warcry", "Buffs", "added_flat",
        subgroup="buff_effect",        stacking_rule="additive",
        ui_priority=76,                source_types=_T,
    ),
    Stat.FOCUS_SKILL_LEVEL: StatMeta(
        "Focus Skill Level", "Buffs", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        stacking_rule="additive",      ui_priority=17,
        source_types=_T,
    ),

    # ── Gear-Specific Stats ───────────────────────────────────────────────────
    Stat.PHYSICAL_DMG_GEAR_INC: StatMeta(
        "Gear Physical Damage", "Gear", "increased", "%",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=10,                source_types=_G,
    ),
    Stat.ENERGY_SHIELD_GEAR_FLAT: StatMeta(
        "Gear Energy Shield", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=31,                source_types=_G,
    ),
    Stat.ENERGY_SHIELD_GEAR_INC: StatMeta(
        "Gear Energy Shield", "Gear", "increased", "%",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=32,                source_types=_G,
    ),
    Stat.WEAPON_ATTACK_SPEED: StatMeta(
        "Weapon Attack Speed", "Gear", "base_stat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=9,                 source_types=_G,
    ),
    Stat.ARMOR_GEAR_FLAT: StatMeta(
        "Gear Armor", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=33,                source_types=_G,
    ),
    Stat.ARMOR_GEAR_INC: StatMeta(
        "Gear Armor", "Gear", "increased", "%",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=34,                source_types=_G,
    ),
    Stat.EVASION_GEAR_FLAT: StatMeta(
        "Gear Evasion", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=35,                source_types=_G,
    ),
    Stat.EVASION_GEAR_INC: StatMeta(
        "Gear Evasion", "Gear", "increased", "%",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=36,                source_types=_G,
    ),
    Stat.PHYSICAL_DMG_GEAR_FLAT_MIN: StatMeta(
        "Gear Physical Damage Min", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=39,                source_types=_G,
    ),
    Stat.PHYSICAL_DMG_GEAR_FLAT_MAX: StatMeta(
        "Gear Physical Damage Max", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=39,                source_types=_G,
    ),
    Stat.FIRE_DMG_GEAR_FLAT_MIN: StatMeta(
        "Gear Fire Damage Min", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=40,                source_types=_G,
    ),
    Stat.FIRE_DMG_GEAR_FLAT_MAX: StatMeta(
        "Gear Fire Damage Max", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=40,                source_types=_G,
    ),
    Stat.COLD_DMG_GEAR_FLAT_MIN: StatMeta(
        "Gear Cold Damage Min", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=41,                source_types=_G,
    ),
    Stat.COLD_DMG_GEAR_FLAT_MAX: StatMeta(
        "Gear Cold Damage Max", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=41,                source_types=_G,
    ),
    Stat.LIGHTNING_DMG_GEAR_FLAT_MIN: StatMeta(
        "Gear Lightning Damage Min", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=42,                source_types=_G,
    ),
    Stat.LIGHTNING_DMG_GEAR_FLAT_MAX: StatMeta(
        "Gear Lightning Damage Max", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=42,                source_types=_G,
    ),
    Stat.EROSION_DMG_GEAR_FLAT_MIN: StatMeta(
        "Gear Erosion Damage Min", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=43,                source_types=_G,
    ),
    Stat.EROSION_DMG_GEAR_FLAT_MAX: StatMeta(
        "Gear Erosion Damage Max", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=43,                source_types=_G,
    ),
    Stat.ELEMENTAL_DMG_GEAR_FLAT_MIN: StatMeta(
        "Gear Elemental Damage Min", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=44,                source_types=_G,
    ),
    Stat.ELEMENTAL_DMG_GEAR_FLAT_MAX: StatMeta(
        "Gear Elemental Damage Max", "Gear", "added_flat",
        subgroup="gear_base",          stacking_rule="additive",
        ui_priority=44,                source_types=_G,
    ),

    # ── Flat Quantity / Mechanic Stats ────────────────────────────────────────
    Stat.MAX_ENERGY_FLAT: StatMeta(
        "Max Energy", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=69,                source_types=("talent_node", "character"),
    ),
    Stat.MAX_CHARGES_FLAT: StatMeta(
        "Max Charges", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=70,                source_types=_TB,
    ),
    Stat.MAX_SPELL_BURST_FLAT: StatMeta(
        "Max Spell Burst", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=71,                source_types=_TB,
    ),
    Stat.EXTRA_JUMPS_FLAT: StatMeta(
        "Jumps", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=72,                source_types=_TB,
    ),

    # ── Skill Levels ──────────────────────────────────────────────────────────
    Stat.PASSIVE_SKILL_LEVEL: StatMeta(
        "Passive Skill Level", "Generic", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("passive",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=16,
        source_types=_T,
    ),
    Stat.EMPOWER_SKILL_LEVEL: StatMeta(
        "Empower Skill Level", "Generic", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("empower",),             affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=16,
        source_types=_T,
    ),
    Stat.DEFENSIVE_SKILL_LEVEL: StatMeta(
        "Defensive Skill Level", "Generic", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("defensive",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=16,
        source_types=_T,
    ),
    Stat.PERSISTENT_SKILL_LEVEL: StatMeta(
        "Persistent Skill Level", "Generic", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("persistent",),          affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=16,
        source_types=_T,
    ),

    # ── Blessings ─────────────────────────────────────────────────────────────
    Stat.MAX_TENACITY_BLESSING_STACKS_FLAT: StatMeta(
        "Max Tenacity Blessing Stacks", "Blessings", "added_flat",
        subgroup="blessing",           stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.MAX_AGILITY_BLESSING_STACKS_FLAT: StatMeta(
        "Max Agility Blessing Stacks", "Blessings", "added_flat",
        subgroup="blessing",           stacking_rule="additive",
        ui_priority=71,                source_types=_T,
    ),
    Stat.MAX_FOCUS_BLESSING_STACKS_FLAT: StatMeta(
        "Max Focus Blessing Stacks", "Blessings", "added_flat",
        subgroup="blessing",           stacking_rule="additive",
        ui_priority=72,                source_types=_T,
    ),

    # ── Attack / Ranged ───────────────────────────────────────────────────────
    Stat.RANGED_DMG_INC: StatMeta(
        "Ranged Damage", "Attack", "increased", "%",
        subgroup="damage",             pipeline_stage="increased_reduced",
        tags=("ranged",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=20,
        source_types=_T,
    ),

    # ── Spell Burst ───────────────────────────────────────────────────────────
    Stat.SPELL_BURST_CHANCE_GAIN_STACKS_FLAT: StatMeta(
        "Spell Burst Chance to Gain Stacks", "Spell", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.SPELL_BURST_HIT_DMG_ADDITIONAL: StatMeta(
        "Spell Burst Hit Damage", "Spell", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        tags=("spell",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=25,
        source_types=_T,
    ),

    # ── Minion (new) ──────────────────────────────────────────────────────────
    Stat.MINION_ELEMENTAL_DMG_INC: StatMeta(
        "Minion Elemental Damage", "Minion", "increased", "%",
        subgroup="damage",             pipeline_stage="increased_reduced",
        tags=("minion",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=20,
        source_types=_T,
    ),
    Stat.MINION_ELEMENTAL_PEN: StatMeta(
        "Minion Elemental Resistance Penetration", "Minion", "penetration", "%",
        subgroup="penetration",        pipeline_stage="mitigation",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=50,
        source_types=_T,
    ),
    Stat.MINION_MOVEMENT_SPEED_INC: StatMeta(
        "Minion Movement Speed", "Minion", "increased", "%",
        subgroup="speed",              stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.MINION_PHYSICAL_DMG_FLAT_MIN: StatMeta(
        "Minion Added Physical Damage Min", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "physical"),   affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_PHYSICAL_DMG_FLAT_MAX: StatMeta(
        "Minion Added Physical Damage Max", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "physical"),   affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_FIRE_DMG_FLAT_MIN: StatMeta(
        "Minion Added Fire Damage Min", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "fire"),       affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_FIRE_DMG_FLAT_MAX: StatMeta(
        "Minion Added Fire Damage Max", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "fire"),       affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_COLD_DMG_FLAT_MIN: StatMeta(
        "Minion Added Cold Damage Min", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "cold"),       affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_COLD_DMG_FLAT_MAX: StatMeta(
        "Minion Added Cold Damage Max", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "cold"),       affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_LIGHTNING_DMG_FLAT_MIN: StatMeta(
        "Minion Added Lightning Damage Min", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "lightning"),  affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_LIGHTNING_DMG_FLAT_MAX: StatMeta(
        "Minion Added Lightning Damage Max", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "lightning"),  affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_EROSION_DMG_FLAT_MIN: StatMeta(
        "Minion Added Erosion Damage Min", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "erosion"),    affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.MINION_EROSION_DMG_FLAT_MAX: StatMeta(
        "Minion Added Erosion Damage Max", "Minion", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("minion", "erosion"),    affects=_HIT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),

    # ── Spirit Magi ───────────────────────────────────────────────────────────
    Stat.SPIRIT_MAGI_INITIAL_GROWTH_FLAT: StatMeta(
        "Spirit Magi Initial Growth", "Spirit Magi", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),

    # ── Elemental Conversion (offensive) ─────────────────────────────────────
    Stat.LIGHTNING_AS_EROSION: StatMeta(
        "Lightning Damage as Erosion Damage", "Lightning", "conversion", "%",
        subgroup="conversion",         pipeline_stage="conversion",
        tags=("lightning",),           affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),
    Stat.COLD_AS_EROSION: StatMeta(
        "Cold Damage as Erosion Damage", "Cold", "conversion", "%",
        subgroup="conversion",         pipeline_stage="conversion",
        tags=("cold",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),
    Stat.FIRE_AS_EROSION: StatMeta(
        "Fire Damage as Erosion Damage", "Fire", "conversion", "%",
        subgroup="conversion",         pipeline_stage="conversion",
        tags=("fire",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=30,
        source_types=_T,
    ),

    # ── Ailments (new) ────────────────────────────────────────────────────────
    Stat.AILMENT_DURATION_INC: StatMeta(
        "Ailment Duration", "Ailments", "increased", "%",
        subgroup="duration",           pipeline_stage="increased_reduced",
        stacking_rule="additive",      ui_priority=50,
        source_types=_T,
    ),
    Stat.IGNITE_DMG_ADDITIONAL: StatMeta(
        "Ignite Damage", "Ailments", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        tags=("ignite",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=20,
        source_types=_T,
    ),
    Stat.IGNITE_DURATION_INC: StatMeta(
        "Ignite Duration", "Ailments", "increased", "%",
        subgroup="duration",           pipeline_stage="increased_reduced",
        tags=("ignite",),              stacking_rule="additive",
        ui_priority=50,                source_types=_T,
    ),
    Stat.IGNITE_EFFECT_RECEIVED_INC: StatMeta(
        "Ignite Effect Received", "Damage Taken", "increased", "%",
        subgroup="ailment_received",   stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.MAX_IGNITE_FLAT: StatMeta(
        "Max Ignite Stacks", "Ailments", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.WILT_DMG_ADDITIONAL: StatMeta(
        "Wilt Damage", "Ailments", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        tags=("wilt",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=20,
        source_types=_T,
    ),

    # ── Trauma (new) ──────────────────────────────────────────────────────────
    Stat.TRAUMA_DMG_ADDITIONAL: StatMeta(
        "Trauma Damage", "Ailments", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        tags=("trauma",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=20,
        source_types=_T,
    ),
    Stat.TRAUMA_BASE_DMG_FLAT_MIN: StatMeta(
        "Added Base Trauma Damage Min", "Ailments", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("trauma",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.TRAUMA_BASE_DMG_FLAT_MAX: StatMeta(
        "Added Base Trauma Damage Max", "Ailments", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("trauma",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.WILT_BASE_DMG_FLAT_MIN: StatMeta(
        "Added Base Wilt Damage Min", "Ailments", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("wilt",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.WILT_BASE_DMG_FLAT_MAX: StatMeta(
        "Added Base Wilt Damage Max", "Ailments", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("wilt",),                affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.IGNITE_BASE_DMG_FLAT_MIN: StatMeta(
        "Added Base Ignite Damage Min", "Ailments", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("ignite",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),
    Stat.IGNITE_BASE_DMG_FLAT_MAX: StatMeta(
        "Added Base Ignite Damage Max", "Ailments", "added_flat",
        subgroup="flat_dmg",           pipeline_stage="flat_damage",
        tags=("ignite",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=5,
        source_types=_T,
    ),

    # ── Channeled / Triggered / Combo (new) ───────────────────────────────────
    Stat.COMBO_FINISHER_CRIT_DMG_INC: StatMeta(
        "Combo Finisher Critical Strike Damage", "Critical Strike", "increased", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("combo",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.COMBO_STARTER_ATTACK_SPEED_ADDITIONAL: StatMeta(
        "Combo Starter Attack Speed", "Attack Speed", "additional", "%",
        subgroup="speed",              tags=("combo",),
        stacking_rule="additive",      ui_priority=40,
        source_types=_T,
    ),
    Stat.COMBO_STARTER_CAST_SPEED_ADDITIONAL: StatMeta(
        "Combo Starter Cast Speed", "Cast Speed", "additional", "%",
        subgroup="speed",              stacking_rule="additive",
        ui_priority=40,                source_types=_T,
    ),
    Stat.COMBO_STARTERS_COMBO_POINTS_FLAT: StatMeta(
        "Combo Points Gained from Combo Starters", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.MIN_CHANNELED_STACKS_FLAT: StatMeta(
        "Min Channeled Stacks", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.JUMP_DMG_FOR_EVERY_ADDITIONAL: StatMeta(
        "Damage per Jump", "Generic", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        stacking_rule="additive",      ui_priority=25,
        source_types=_T,
    ),

    # ── Life ─────────────────────────────────────────────────────────────────
    Stat.MAX_LIFE_ADDITIONAL: StatMeta(
        "Max Life", "Life", "additional", "%",
        subgroup="max",                pipeline_stage="additional",
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),

    # ── Defense (new) ─────────────────────────────────────────────────────────
    Stat.ARMOR_ADDITIONAL: StatMeta(
        "Armor", "Defense", "additional", "%",
        subgroup="armor",              stacking_rule="additive",
        ui_priority=10,                source_types=_T,
    ),
    Stat.EVASION_ADDITIONAL: StatMeta(
        "Evasion", "Defense", "additional", "%",
        subgroup="evasion",            stacking_rule="additive",
        ui_priority=15,                source_types=_T,
    ),
    Stat.SHIELD_DEFENSE_ADDITIONAL: StatMeta(
        "Shield Defense", "Defense", "additional", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=30,                source_types=_T,
    ),
    Stat.ARMOR_EFFECTIVE_RATE_NON_PHYSICAL_INC: StatMeta(
        "Armor Effective Rate for Non-Physical Damage", "Defense", "increased", "%",
        subgroup="armor",              stacking_rule="additive",
        ui_priority=20,                source_types=_T,
    ),

    # ── Damage Taken Conversion (new) ─────────────────────────────────────────
    Stat.PHYSICAL_TAKEN_AS_LIGHTNING_INC: StatMeta(
        "Physical Damage Taken as Lightning", "Damage Taken", "conversion", "%",
        subgroup="conversion",         stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.PHYSICAL_TAKEN_AS_COLD_INC: StatMeta(
        "Physical Damage Taken as Cold", "Damage Taken", "conversion", "%",
        subgroup="conversion",         stacking_rule="additive",
        ui_priority=61,                source_types=_T,
    ),
    Stat.PHYSICAL_TAKEN_AS_FIRE_INC: StatMeta(
        "Physical Damage Taken as Fire", "Damage Taken", "conversion", "%",
        subgroup="conversion",         stacking_rule="additive",
        ui_priority=62,                source_types=_T,
    ),
    Stat.EROSION_TAKEN_AS_LIGHTNING_INC: StatMeta(
        "Erosion Damage Taken as Lightning", "Damage Taken", "conversion", "%",
        subgroup="conversion",         stacking_rule="additive",
        ui_priority=63,                source_types=_T,
    ),
    Stat.EROSION_TAKEN_AS_COLD_INC: StatMeta(
        "Erosion Damage Taken as Cold", "Damage Taken", "conversion", "%",
        subgroup="conversion",         stacking_rule="additive",
        ui_priority=64,                source_types=_T,
    ),
    Stat.EROSION_TAKEN_AS_FIRE_INC: StatMeta(
        "Erosion Damage Taken as Fire", "Damage Taken", "conversion", "%",
        subgroup="conversion",         stacking_rule="additive",
        ui_priority=65,                source_types=_T,
    ),

    # ── Buffs / Utility ───────────────────────────────────────────────────────
    Stat.MAX_CURSE_FLAT: StatMeta(
        "Max Curses", "Buffs", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.CURSE_EFFECT_AGAINST_INC: StatMeta(
        "Curse Effect Against You", "Buffs", "increased", "%",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=65,                source_types=_T,
    ),
    Stat.TAUNT_ON_HIT_CHANCE: StatMeta(
        "Chance to Taunt on Hit", "Utility", "chance", "%",
        subgroup="mechanics",          stacking_rule="additive_chance",
        ui_priority=65,                source_types=_TB,
    ),
    Stat.ATTACK_TAUNT_ON_HIT_CHANCE: StatMeta(
        "Attack Chance to Taunt on Hit", "Utility", "chance", "%",
        subgroup="mechanics",          stacking_rule="additive_chance",
        ui_priority=65,                source_types=_TB,
    ),

    # ── Utility / Mechanic Stats (new) ────────────────────────────────────────
    Stat.MAX_TERRA_CHARGE_STACKS_FLAT: StatMeta(
        "Max Terra Charge Stacks", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.TERRA_CHARGE_RECOVERY_SPEED_INC: StatMeta(
        "Terra Charge Recovery Speed", "Utility", "increased", "%",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=61,                source_types=_T,
    ),
    Stat.MAX_TERRA_QUANTITY_FLAT: StatMeta(
        "Max Terra Quantity", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=62,                source_types=_T,
    ),
    Stat.MAX_WARCRY_SKILL_CHARGES_FLAT: StatMeta(
        "Max Warcry Skill Charges", "Buffs", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_T,
    ),
    Stat.MAX_SHADOW_QUANTITY_FLAT: StatMeta(
        "Max Shadow Quantity", "Utility", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=63,                source_types=_T,
    ),
    Stat.SHADOW_DMG_ADDITIONAL: StatMeta(
        "Shadow Damage", "Generic", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        stacking_rule="additive",      ui_priority=25,
        source_types=_T,
    ),
    Stat.DMG_TO_LIFE_ADDITIONAL: StatMeta(
        "Damage Applied to Life", "Generic", "additional", "%",
        subgroup="damage",             stacking_rule="additive",
        ui_priority=30,                source_types=_T,
    ),
    Stat.ELIXIR_CHARGING_PROGRESS_FLAT: StatMeta(
        "Elixir Charging Progress per Second", "Buffs", "added_flat",
        subgroup="mechanics",          stacking_rule="additive",
        ui_priority=60,                source_types=_TB,
    ),
    Stat.BEAM_DMG_ADDITIONAL: StatMeta(
        "Beam Damage", "Generic", "additional", "%",
        subgroup="damage",             pipeline_stage="additional",
        stacking_rule="additive",      ui_priority=25,
        source_types=_T,
    ),

    # ── Skill Levels ─────────────────────────────────────────────────────────
    Stat.MAIN_SKILL_LEVEL: StatMeta(
        "Main Skill Level", "Generic", "added_flat",
        subgroup="skill_level",        stacking_rule="additive",
        ui_priority=80,                source_types=_T,
    ),
}


# ── All valid category names ───────────────────────────────────────────────────
CATEGORIES: list[str] = [
    "Attributes",
    "Generic",
    "Attack",
    "Spell",
    "Melee",
    "Area",
    "Projectile",
    "Minion",
    "Sentry",
    "Spirit Magi",
    "Physical",
    "Lightning",
    "Cold",
    "Fire",
    "Erosion",
    "Elemental",
    "Ailments",
    "Steep Strike",
    "Cast Speed",
    "Attack Speed",
    "Critical Strike",
    "Life",
    "Mana",
    "Energy Shield",
    "Defense",
    "Damage Taken",
    "Buffs",
    "Gear",
    "Utility",
    "Blessings",
]

# ── modifier_type reference ────────────────────────────────────────────────────
# "base_stat"     — raw attribute (STR/DEX/INT); feeds attribute stage
# "added_flat"    — flat additive value (flat dmg, flat life/mana/armor)
# "increased"     — additive % pool; feeds increased_reduced stage for damage stats
# "additional"    — independent multiplicative bucket; feeds additional stage
# "chance"        — additive probability (double dmg, crit chance)
# "skill_level"   — additive level bonus; feeds skill_level stage
# "penetration"   — additive resistance/armor reduction
# "crit_rating"   — feeds crit_rating stage (CSR calculation)
# "crit_damage"   — feeds crit_damage stage (crit multiplier)
# "conversion"    — physical → elemental conversion or damage-type taken conversion
#
# pipeline_stage reference:
# "base"              — skill base damage at its current level (not from nodes)
# "added_flat"        — flat damage added to base
# "increased_reduced" — single (1 + Σinc - Σred) factor; all increased stats pool here
# "additional"        — each distinct additional stat = own (1 + Σwithin) factor
# "attribute"         — (1 + total_attr_points × 0.005) for tag-matched skills
# "skill_level"       — summed level bonus → levels_above_30 → skill_multiplier
# "crit_rating"       — CSR → crit_chance = min(CSR/100, 1.0)
# "crit_damage"       — crit multiplier; default 150%; additive pool
# "double_damage"     — (1 + Σchance) Hit-only expected value factor
# "penetration"       — elemental: eff_res = enemy_res - Σpen; additive total
# "mitigation"        — final: armor (physical) or resistance (elemental)
# ""                  — not part of damage pipeline (speed, defense, life, mana)
