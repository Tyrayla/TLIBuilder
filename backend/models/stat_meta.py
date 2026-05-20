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

    # ── Attributes ────────────────────────────────────────────────────────────
    # Each point = 0.5% additional damage for tag-matched skills.
    # The pipeline sums relevant attribute points → attr_factor = 1 + total × 0.005.
    Stat.STRENGTH: StatMeta(
        "Strength", "Attributes", "base_stat",
        subgroup="attribute",     pipeline_stage="attribute",
        affects=_HIT_DOT,         stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.DEXTERITY: StatMeta(
        "Dexterity", "Attributes", "base_stat",
        subgroup="attribute",     pipeline_stage="attribute",
        affects=_HIT_DOT,         stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),
    Stat.INTELLIGENCE: StatMeta(
        "Intelligence", "Attributes", "base_stat",
        subgroup="attribute",     pipeline_stage="attribute",
        affects=_HIT_DOT,         stacking_rule="additive",
        ui_priority=5,            source_types=_TB,
    ),

    # ── Generic ───────────────────────────────────────────────────────────────
    Stat.ARMOR_PEN: StatMeta(
        "Armor Penetration", "Generic", "penetration", "%",
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
        "Increased Damage", "Generic", "increased", "%",
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
    Stat.ALL_SKILL_LEVEL: StatMeta(
        "All Skill Level", "Generic", "skill_level",
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

    # ── Attack ────────────────────────────────────────────────────────────────
    Stat.ATTACK_DMG_INC: StatMeta(
        "Increased Attack Damage", "Attack", "increased", "%",
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

    # ── Spell ─────────────────────────────────────────────────────────────────
    Stat.SPELL_DMG_INC: StatMeta(
        "Increased Spell Damage", "Spell", "increased", "%",
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

    # ── Melee ─────────────────────────────────────────────────────────────────
    Stat.MELEE_DMG_INC: StatMeta(
        "Increased Melee Damage", "Melee", "increased", "%",
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
        "Increased Area Damage", "Area", "increased", "%",
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
        "Increased Projectile Damage", "Projectile", "increased", "%",
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
        "Increased Projectile Speed", "Projectile", "increased", "%",
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

    # ── Minion ────────────────────────────────────────────────────────────────
    Stat.MINION_DMG_INC: StatMeta(
        "Increased Minion Damage", "Minion", "increased", "%",
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
    Stat.SYNTH_DOUBLE_DMG_CHANCE: StatMeta(
        "Synthetic Troop Double Damage Chance", "Minion", "chance", "%",
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

    # ── Sentry ────────────────────────────────────────────────────────────────
    Stat.SENTRY_DMG_ADDITIONAL: StatMeta(
        "Additional Sentry Damage", "Sentry", "additional", "%",
        subgroup="sentry_damage",      pipeline_stage="additional",
        tags=("sentry",),              affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=10,
        source_types=_T,
    ),
    Stat.SENTRY_SKILL_CAST_FREQUENCY_INC: StatMeta(
        "Increased Sentry Cast Frequency", "Sentry", "increased", "%",
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

    # ── Physical ──────────────────────────────────────────────────────────────
    Stat.PHYSICAL_DMG_INC: StatMeta(
        "Increased Physical Damage", "Physical", "increased", "%",
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
        ui_priority=80,                source_types=_T,
    ),
    Stat.PHYSICAL_AS_COLD: StatMeta(
        "Physical as Cold", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "cold"),
        ui_priority=80,                source_types=_T,
    ),
    Stat.PHYSICAL_AS_FIRE: StatMeta(
        "Physical as Fire", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "fire"),
        ui_priority=80,                source_types=_T,
    ),
    Stat.PHYSICAL_AS_EROSION: StatMeta(
        "Physical as Erosion", "Physical", "conversion", "%",
        subgroup="conversion",         tags=("physical", "erosion"),
        ui_priority=80,                source_types=_T,
    ),
    Stat.PHYSICAL_SKILL_LEVEL: StatMeta(
        "Physical Skill Level", "Physical", "skill_level",
        subgroup="skill_level",        pipeline_stage="skill_level",
        tags=("physical",),            affects=_HIT_DOT,
        stacking_rule="additive",      ui_priority=15,
        source_types=_T,
    ),

    # ── Lightning ─────────────────────────────────────────────────────────────
    Stat.LIGHTNING_DMG_INC: StatMeta(
        "Increased Lightning Damage", "Lightning", "increased", "%",
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

    # ── Cold ──────────────────────────────────────────────────────────────────
    Stat.COLD_DMG_INC: StatMeta(
        "Increased Cold Damage", "Cold", "increased", "%",
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

    # ── Fire ──────────────────────────────────────────────────────────────────
    Stat.FIRE_DMG_INC: StatMeta(
        "Increased Fire Damage", "Fire", "increased", "%",
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

    # ── Erosion ───────────────────────────────────────────────────────────────
    Stat.EROSION_DMG_INC: StatMeta(
        "Increased Erosion Damage", "Erosion", "increased", "%",
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

    # ── Elemental ─────────────────────────────────────────────────────────────
    # "elemental" tag = applies when skill has any of fire/cold/lightning/erosion
    Stat.ELEMENTAL_DMG_INC: StatMeta(
        "Increased Elemental Damage", "Elemental", "increased", "%",
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
        "Increased Cast Speed", "Cast Speed", "increased", "%",
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
        "Increased Attack Speed", "Attack Speed", "increased", "%",
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

    # ── Critical Strike ───────────────────────────────────────────────────────
    # CSR calc: base_CSR × (1 + Σ crit_rating_inc) × independent additional factors
    # Crit chance = CSR_final / 100; default crit damage = 150%
    Stat.ATTACK_CRIT_RATING_GEAR: StatMeta(
        "Attack Crit Rating (Gear)", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_G,
    ),
    Stat.ATTACK_CRIT_RATING_MH: StatMeta(
        "Attack Crit Rating (Main Hand)", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_G,
    ),
    Stat.ATTACK_CRIT_RATING_INC: StatMeta(
        "Increased Attack Crit Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.SPELL_CRIT_RATING_INC: StatMeta(
        "Increased Spell Crit Rating", "Critical Strike", "crit_rating", "%",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("spell",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=11,
        source_types=_T,
    ),
    Stat.MINION_CRIT_RATING_INC: StatMeta(
        "Increased Minion Crit Rating", "Critical Strike", "crit_rating", "%",
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
        "Spirit Magi Crit Rating", "Critical Strike", "crit_rating",
        subgroup="crit_rating",        pipeline_stage="crit_rating",
        tags=("spirit_magi",),         affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_TB,
    ),
    Stat.CRIT_DMG: StatMeta(
        "Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        affects=_HIT,                  stacking_rule="additive",
        ui_priority=12,                source_types=_T,
    ),
    Stat.ATTACK_CRIT_DMG: StatMeta(
        "Attack Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("attack",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.SPELL_CRIT_DMG: StatMeta(
        "Spell Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("spell",),               affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.MINION_CRIT_DMG: StatMeta(
        "Minion Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("minion",),              affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.PHYS_CRIT_DMG: StatMeta(
        "Physical Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("physical",),            affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.LIGHTNING_CRIT_DMG: StatMeta(
        "Lightning Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("lightning",),           affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.COLD_CRIT_DMG: StatMeta(
        "Cold Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("cold",),                affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.FIRE_CRIT_DMG: StatMeta(
        "Fire Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("fire",),                affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),
    Stat.EROSION_CRIT_DMG: StatMeta(
        "Erosion Critical Strike Damage", "Critical Strike", "crit_damage", "%",
        subgroup="crit_damage",        pipeline_stage="crit_damage",
        tags=("erosion",),             affects=_HIT,
        stacking_rule="additive",      ui_priority=12,
        source_types=_T,
    ),

    # ── Life ──────────────────────────────────────────────────────────────────
    Stat.MAX_LIFE: StatMeta(
        "Maximum Life", "Life", "added_flat",
        subgroup="life",               stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.MAX_LIFE_INC: StatMeta(
        "Increased Maximum Life", "Life", "increased", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=32,                source_types=_T,
    ),
    Stat.LIFE_REGEN_FLAT: StatMeta(
        "Life Regeneration", "Life", "added_flat",
        subgroup="life",               stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.LIFE_REGEN_INC: StatMeta(
        "Increased Life Regeneration", "Life", "increased", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.LIFE_LEECH_RATE: StatMeta(
        "Life Leech Rate", "Life", "chance", "%",
        subgroup="life",               stacking_rule="additive",
        ui_priority=35,                source_types=_T,
    ),

    # ── Mana ──────────────────────────────────────────────────────────────────
    Stat.MAX_MANA: StatMeta(
        "Maximum Mana", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.MAX_MANA_INC: StatMeta(
        "Increased Maximum Mana", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=32,                source_types=_T,
    ),
    Stat.MANA_REGEN_FLAT: StatMeta(
        "Mana Regeneration", "Mana", "added_flat",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.MANA_REGEN_INC: StatMeta(
        "Increased Mana Regeneration", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=34,                source_types=_T,
    ),
    Stat.SKILL_COST_REDUCTION: StatMeta(
        "Skill Cost Reduction", "Mana", "increased", "%",
        subgroup="mana",               stacking_rule="additive",
        ui_priority=35,                source_types=_T,
    ),

    # ── Defense ───────────────────────────────────────────────────────────────
    Stat.ARMOR: StatMeta(
        "Armor", "Defense", "added_flat",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=31,                source_types=_TB,
    ),
    Stat.ELEMENTAL_RESISTANCE: StatMeta(
        "Elemental Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=32,                source_types=_TB,
    ),
    Stat.FIRE_RESISTANCE: StatMeta(
        "Fire Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.COLD_RESISTANCE: StatMeta(
        "Cold Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.LIGHTNING_RESISTANCE: StatMeta(
        "Lightning Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),
    Stat.EROSION_RESISTANCE: StatMeta(
        "Erosion Resistance", "Defense", "added_flat", "%",
        subgroup="defense",            stacking_rule="additive",
        ui_priority=33,                source_types=_TB,
    ),

    # ── Utility ───────────────────────────────────────────────────────────────
    Stat.MOVEMENT_SPEED_INC: StatMeta(
        "Increased Movement Speed", "Utility", "increased", "%",
        subgroup="speed",              stacking_rule="additive",
        ui_priority=61,                source_types=_T,
    ),
    Stat.COOLDOWN_REDUCTION_INC: StatMeta(
        "Cooldown Reduction", "Utility", "increased", "%",
        subgroup="utility",            stacking_rule="additive",
        ui_priority=62,                source_types=_T,
    ),

    # ── Blessings ─────────────────────────────────────────────────────────────
    Stat.TENACITY_BLESSING: StatMeta(
        "Tenacity Blessing", "Blessings", "added_flat",
        subgroup="blessing",           stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.AGILITY_BLESSING: StatMeta(
        "Agility Blessing", "Blessings", "added_flat",
        subgroup="blessing",           stacking_rule="additive",
        ui_priority=70,                source_types=_T,
    ),
    Stat.FOCUS_BLESSING: StatMeta(
        "Focus Blessing", "Blessings", "added_flat",
        subgroup="blessing",           stacking_rule="additive",
        ui_priority=70,                source_types=_T,
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
    "Physical",
    "Lightning",
    "Cold",
    "Fire",
    "Erosion",
    "Elemental",
    "Steep Strike",
    "Cast Speed",
    "Attack Speed",
    "Critical Strike",
    "Life",
    "Mana",
    "Defense",
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
# "skill_multiply"— independent ×1.08 per point; for (multiplies) tagged sources
# "penetration"   — additive resistance/armor reduction
# "crit_rating"   — feeds crit_rating stage (CSR calculation)
# "crit_damage"   — feeds crit_damage stage (crit multiplier)
# "conversion"    — physical → elemental conversion (deferred, not in pipeline v1)
#
# pipeline_stage reference:
# "base"              — skill base damage at its current level (not from nodes)
# "added_flat"        — flat damage added to base
# "increased_reduced" — single (1 + Σinc - Σred) factor; all increased stats pool here
# "additional"        — each distinct additional stat = own (1 + Σwithin) factor
# "attribute"         — (1 + total_attr_points × 0.005) for tag-matched skills
# "skill_level"       — summed level bonus → levels_above_30 → skill_multiplier
# "skill_multiply"    — 1.08^n per extra level 31+; also (multiplies) sources
# "crit_rating"       — CSR → crit_chance = min(CSR/100, 1.0)
# "crit_damage"       — crit multiplier; default 150%; additive pool
# "double_damage"     — (1 + Σchance) Hit-only expected value factor
# "penetration"       — elemental: eff_res = enemy_res - Σpen; additive total
# "mitigation"        — final: armor (physical) or resistance (elemental)
# ""                  — not part of damage pipeline (speed, defense, life, mana)
