from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Literal
import re


@dataclass
class SkillHitForm:
    name: str
    effectiveness_pct: float       # at a specific level, before above-max scaling
    form_type: Literal["additive", "exclusive"]
    proc_stat_key: str | None = None
    # "steep_strike_chance"               → fires when steep procs
    # "_complement_steep_strike_chance"   → fires when steep does NOT proc (= 1 - steep_chance)
    # None                                → additive form; always fires
    # ── Multi-form SPELL base (set per form when a spell has several intrinsic base-damage forms, e.g.
    #    Icebound Beam's Cold Beam + Icy Blade). When base_dmg is set, offense computes THIS form's flat
    #    from its own base + the shared added flat scaled by `added_eff` (per-form effectiveness), instead
    #    of the skill-wide base. effectiveness_pct stays 100 for spells (no eff double-dip on base). ──
    base_dmg: dict[str, tuple[float, float]] | None = None  # {dtype: (min, max)} intrinsic per-level base
    added_eff: float | None = None    # this form's added-damage effectiveness (1.19 = 119%); None → skill-wide
    # ── Channeled cadence (set on channeled skills) ──
    channel_role: str | None = None   # "continuous" → fires every use; "burst" → once per RESET cycle; None → every use
    hit_count: int = 1                # BASE projectiles/blades fired per occurrence (Icy Blade base = 2)
    shotgun_falloff: float = 0.0      # same-target Shotgun Effect falloff coefficient (0.65 = each subsequent hit −65%)
    scales_with_projectiles: bool = False  # if True, hit_count += projectile_quantity_flat (the blades shotgun a target)


@dataclass
class IntrinsicAdditional:
    """A skill-intrinsic 'additional damage' pool that scales with a rating value. The rating comes
    from a numeric condition (rating_source='condition', e.g. Focused Slash's Fervor Rating) or from
    an aggregated stat (rating_source='stat', e.g. Moon Strike's Max Mana). Evaluated in compute.py
    (which has both the source and the condition state) and applied as one extra additional pool in
    calculate_offense:
        bonus_fraction = min(per * (rating / per_n) * (1 + effect_value), cap)
    """
    per: float                        # additional fraction per unit of (rating / per_n) — 0.004 = 0.4%
    rating_key: str                   # condition or stat key supplying the scaling value
    rating_source: str = "condition"  # "condition" (condition_state) or "stat" (source.total)
    per_n: float = 1.0                # divide the rating by this first (e.g. 100 → per 100 Max Mana)
    cap: float | None = None          # max bonus fraction, e.g. 0.70 = +70%
    effect_key: str | None = None     # optional INCREASED % stat scaling the bonus (e.g. 'fervor_effect_inc')
    skill_effect_key: str | None = None  # optional SKILL-LOCAL increased % stat, added into the SAME
                                      # increased pool as effect_key (e.g. 'fervor_effect_skill_inc' for
                                      # Focused Slash: Tranquility) — scales the skill's bonus, not crit
    label: str = ""                   # display label for the additional-damage breakdown line (e.g. Rapid
                                      # Advance's per-Max-Channeled-Stack bonus); blank → generic "Skill Intrinsic"


@dataclass
class ChanneledSpec:
    """A channeled skill's stack behaviour, declared by its resolver (the per-skill module). Consumed by
    offense to set per-form cadence (see engine/uptime.channeled_rounds_per_cycle and the framework plan).

      - behavior "reset"   → at max, dump ALL stacks and fire the burst form; cycle = ramp 0→max repeatedly.
      - behavior "refresh" → hold at max while channeling; continuous damage scales at `max` stacks.

    max/min are the BASE (intrinsic) values; offense adds max_channeled_stacks_flat / min_channeled_stacks_flat
    from the build. `max_from_data` False means the skill line omitted the cap and the module hardcodes it
    (Icebound Beam: normally "Channels up to 5 stacks", lost in the SS12 DB → fallback 5).
    """
    max_stacks: int
    min_stacks: int = 0
    behavior: Literal["reset", "refresh"] = "reset"
    max_from_data: bool = False
    # RESET only: does the use that reaches max ALSO fire the continuous form, or replace it with the burst?
    # Icebound Beam: ADDITIVE (Tyra-confirmed — the Icy Blades fire while the beam is still going).
    burst_replaces_continuous: bool = False
    # RESET only: when the burst form actually fires (projectile_count ≥ 1), the CONTINUOUS form's damage is
    # suppressed to this fraction (the channel "redistributes" beam damage into the blades). 1.0 = no
    # suppression. Icebound Beam: 1/3 — validated in-game (beam 113 solo → ~38 steady-state once blades fire;
    # 0/1/2/4/6-projectile recounts all fit beam×(1/3) + additive blades to within ~2%).
    continuous_suppression_when_bursting: float = 1.0
    # Persistent-entity strike rate (e.g. Howling Gale's "Base Attack Frequency 1.5"). When set, the CONTINUOUS
    # form fires at `attack_frequency × cast-speed multiplier` (the spawned entity's rate), NOT the channel cast
    # rate (sps); sps stays the stack-build rate, shown separately. None → the form fires at sps (Icebound).
    attack_frequency: float | None = None


@dataclass
class ResolvedSkill:
    skill_id: str
    name: str
    tags: list[str]
    max_level: int
    hit_forms_by_level: dict[int, list[SkillHitForm]]
    supported: bool = True  # False when skill_id is not in registry
    channeled: "ChanneledSpec | None" = None  # set on channeled skills (Icebound Beam, …)
    base_steep_strike_chance: float = 0.0  # intrinsic passive from skill text (e.g. "This skill +20% Steep Strike chance")
    intrinsic_additional: list[IntrinsicAdditional] = field(default_factory=list)
    # Projectile-scaling form has NO Shotgun Effect by default ("the Projectiles shot by this skill cannot hit the
    # same enemy") → single-target hit count is 1 until a support grants Shotgun Effect (emits
    # same_target_shotgun_grant). Distinct from spread/trajectory. Chromatic Shot / Icebound keep their innate
    # shotgun (they do NOT set this). Split Shot base sets it True; Volley flips it on. See engine/offense.py.
    shotgun_requires_grant: bool = False
    # Extra tags merged into the skill's tag set ONLY for damage increased/additional filtering, so a
    # skill can benefit from off-type damage mods. E.g. Moon Strike: ['spell'] → Spell Damage
    # inc/additional apply to its Attack Damage (without making it count as a spell for flat adds).
    extra_damage_mod_tags: list[str] = field(default_factory=list)
    # ── Spell pathway (set by spell resolvers; defaults keep the attack path unchanged) ──
    # Spells have intrinsic base damage and a cast-speed hit rate, unlike weapon attacks. See
    # docs/CHAIN_LIGHTNING_IMPLEMENTATION_PLAN.md §1.
    is_spell: bool = False
    base_dmg_by_level: dict[int, dict[str, tuple[float, float]]] = field(default_factory=dict)  # level → {dtype: (min,max)}
    base_cast_time: float = 0.0                 # seconds per cast (e.g. 0.65)
    added_dmg_effectiveness: float = 1.0        # 136% → 1.36; applied to ADDED flat only, NOT base
    damage_types: list[str] = field(default_factory=list)  # e.g. ["lightning"]
    jumps_base: int = 0                         # base Jumps (e.g. Chain Lightning +2); displayed in Skill Effects
    mana_cost: float = 0.0                       # base per-cast Mana Cost magnitude (e.g. 15, or 15 for "15%")
    mana_cost_is_percent: bool = False           # True when the base cost is a % of Max Mana (e.g. "15%" / channeled)
    intrinsic_mana_to_life: float = 0.0          # skill-LOCAL Arcane (Bull's Rage: "All Mana costs … converted to Life
                                                 # costs" → 1.0). The conversion happens BEFORE the %-base resolves, so
                                                 # a "15%" base becomes 15% of Max LIFE (see engine.skill_cost).
    demolisher_base_restore: float = 0.0         # Demolisher skills: base seconds to restore 1 Demolisher Charge
                                                 # (Groundshaker 3s). 0 = not a Demolisher skill. See engine.compute.
    # Main attribute(s) for this skill, lowercased (e.g. ["dexterity", "intelligence"]). Each point of
    # a main-stat attribute grants +0.5% damage to this skill; multi-main-stat skills SUM the attribute
    # totals before applying. Source: TLI Help DB (Strength/Dexterity/Intelligence). Parsed in
    # resolve_skill from the skill's `main_stat` field; consumed by calculate_offense.
    main_stat: list[str] = field(default_factory=list)
    # Compulsory (random/rotated) elemental conversion (Chromatic Shot): each cast deals ONE of these elements,
    # bypassing normal conversion — ALL added flat (any type) folds into base first, then only the final element's
    # increased/additional apply. offense computes each element fully and reports the expected average. Empty = off.
    compulsory_elements: list[str] = field(default_factory=list)
    base_flat_by_level: dict[int, tuple[float, float]] = field(default_factory=dict)  # type-agnostic base for compulsory


_REGISTRY: dict[str, Callable[[dict], ResolvedSkill]] = {}


def _register(skill_id: str):
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[skill_id] = fn
        return fn
    return decorator


# ── Slash-Strike skills (Berserking Blade, Focused Slash) ──────────────────────
# Both have the same two mutually-exclusive forms per cast: Sweep Slash (fires when Steep does NOT
# proc) | Steep Strike (fires on the Steep proc). The form text differs slightly between skills —
# "Sweep Slash: 210% Weapon Attack Damage" vs "Sweep Slash: Deals 154% Weapon Attack Damage" —
# so the optional "Deals " is part of the regex.
_BB_FORM_RE = re.compile(
    r"([A-Z][A-Za-z ]+):\s*(?:Deals\s+)?(\d+(?:\.\d+)?)%\s*Weapon Attack Damage", re.IGNORECASE
)
_SKILL_STEEP_CHANCE_RE = re.compile(
    r"This skill \+(\d+(?:\.\d+)?)\s*%\s*Steep Strike chance", re.IGNORECASE
)


def _resolve_slash_skill(
    skill_data: dict,
    intrinsic_additional: list[IntrinsicAdditional] | None = None,
    extra_damage_mod_tags: list[str] | None = None,
) -> ResolvedSkill:
    """Shared resolver for the Sweep Slash / Steep Strike skill family."""
    max_level = skill_data.get("max_level", 20)
    progression = {
        entry["level"]: entry["values"]
        for entry in skill_data.get("progression", [])
    }
    forms_by_level: dict[int, list[SkillHitForm]] = {}
    for lvl, values in progression.items():
        matches = _BB_FORM_RE.findall(values.get("Descript", ""))
        if len(matches) != 2:
            raise ValueError(
                f"{skill_data.get('item_id', '?')}: expected 2 hit forms at level {lvl}, "
                f"got {len(matches)}: {values.get('Descript', '')!r}"
            )
        # matches[0] = Sweep Slash (fires when steep does NOT proc)
        # matches[1] = Steep Strike (fires when steep procs)
        forms_by_level[lvl] = [
            SkillHitForm(matches[0][0].strip(), float(matches[0][1]), "exclusive", "_complement_steep_strike_chance"),
            SkillHitForm(matches[1][0].strip(), float(matches[1][1]), "exclusive", "steep_strike_chance"),
        ]
    m = _SKILL_STEEP_CHANCE_RE.search(skill_data.get("raw_text", ""))
    base_steep = float(m.group(1)) / 100.0 if m else 0.0

    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        base_steep_strike_chance=base_steep,
        intrinsic_additional=intrinsic_additional or [],
        extra_damage_mod_tags=extra_damage_mod_tags or [],
    )


# Berserking Blade — Tags: Attack, Melee, Area, Physical, Slash-Strike, Persistent.
# (Its "50% chance for an extra buff stack on hit" mechanic is unmodeled, like other secondary procs.)
@_register("berserking_blade")
def _resolve_berserking_blade(skill_data: dict) -> ResolvedSkill:
    return _resolve_slash_skill(skill_data)


# Focused Slash — Tags: Attack, Melee, Area, Physical, Slash-Strike.
# Intrinsic Fervor bonus: "+0.4% additional damage for this skill per 1 Fervor Rating, affected by
# Fervor Effect" → one additional pool = 0.004 * fervor_rating * (1 + fervor_effect_inc).
@_register("focused_slash")
def _resolve_focused_slash(skill_data: dict) -> ResolvedSkill:
    return _resolve_slash_skill(
        skill_data,
        [IntrinsicAdditional(per=0.004, rating_key="fervor_rating", effect_key="fervor_effect_inc",
                             skill_effect_key="fervor_effect_skill_inc")],
    )


# Moon Strike — Tags: Attack, Area, Physical, Melee, Slash-Strike. Two baseline quirks:
#  - "Spell Damage bonus and additional bonus also apply to the skill's Attack Damage" → borrow ALL
#    Spell Damage inc/additional mods via extra tag 'spell' (each still gated by its own condition).
#  - "+1% additional damage per 100 Max Mana, up to +70%" → mana-scaled intrinsic additional pool.
@_register("moon_strike")
def _resolve_moon_strike(skill_data: dict) -> ResolvedSkill:
    return _resolve_slash_skill(
        skill_data,
        intrinsic_additional=[IntrinsicAdditional(
            per=0.01, rating_key="max_mana", rating_source="stat", per_n=100.0, cap=0.70,
        )],
        extra_damage_mod_tags=["spell"],
    )


# ── Groundshaker (Demolisher attack) ─────────────────────────────────────────────
# Tags: Attack, Melee, Area, Physical, Demolisher. Two WAD-scaled hit forms per cast, both additive:
#   Primary Fissure  (the pummel, "Fission: Deals N% Weapon Attack Damage") — lands EVERY cast.
#   Secondary Explosion ("Fissure Secondary Damage: Deals M% Weapon Attack Damage") — only on a CHARGED
#   (consume) cast. The charged-cast gating + rate + Frequent-Quake/Collapse/Cripple interactions are handled
#   by the demolisher offense mode (engine.offense + engine.compute); the resolver only supplies the two hits
#   + the base Demolisher-Charge restoration time.
_GS_RESTORE_RE = re.compile(r"gains?\s+\d+\s+demolisher\s+charge\s+every\s+([\d.]+)\s*s", re.IGNORECASE)


@_register("groundshaker")
def _resolve_groundshaker(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {entry["level"]: entry["values"] for entry in skill_data.get("progression", [])}
    forms_by_level: dict[int, list[SkillHitForm]] = {}
    for lvl, values in progression.items():
        matches = _BB_FORM_RE.findall(values.get("Descript", ""))
        if len(matches) != 2:
            raise ValueError(
                f"{skill_data.get('item_id', '?')}: expected 2 Groundshaker hit forms at level {lvl}, "
                f"got {len(matches)}: {values.get('Descript', '')!r}")
        # matches[0] = Fission (primary fissure), matches[1] = Fissure Secondary Damage (secondary explosion).
        forms_by_level[lvl] = [
            SkillHitForm("Primary Fissure", float(matches[0][1]), "additive"),
            SkillHitForm("Secondary Explosion", float(matches[1][1]), "additive"),
        ]
    m = _GS_RESTORE_RE.search(skill_data.get("raw_text", "") or "")
    base_restore = float(m.group(1)) if m else 3.0
    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        demolisher_base_restore=base_restore,
    )


# ── Split Shot (projectile attack) ───────────────────────────────────────────────
# Tags: Attack, Projectile, Physical, Ranged, Horizontal. Main stat Dexterity. Fires 1 + intrinsic "+2 Projectile
# Quantity" = 3 projectiles, dealing a per-level % Weapon Attack Damage (237% @L1 → 347% @L20). Base state
# spreads and "the Projectiles shot by this skill cannot hit the same enemy" → NO Shotgun Effect (single-target
# hit count 1) until Volley grants it. The skill DEFINES a dormant Shotgun Effect falloff coefficient of 77% (in
# the engine's convention that coefficient is the fraction LOST, so a granted subsequent projectile deals 1−0.77).
# Rapid Advance turns it channeled (installed at slot time by skill_effects/split_shot.py). On-kill extra
# projectiles (50%/8m/2 targets) are a clear/AoE mechanic → NYI.
_SPLIT_SHOT_WAD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*weapon\s+attack\s+damage", re.IGNORECASE)
_SPLIT_SHOT_FALLOFF = 0.77   # in-game "falloff coefficient" — engine convention: subsequent hit deals (1 − this)


@_register("split_shot")
def _resolve_split_shot(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {entry["level"]: entry["values"] for entry in skill_data.get("progression", [])}
    forms_by_level: dict[int, list[SkillHitForm]] = {}
    for lvl, values in progression.items():
        # WAD % lives in "Effectiveness of added damage" / "damage" / "Descript" — search all values.
        text = " ".join(str(v) for v in values.values())
        m = _SPLIT_SHOT_WAD_RE.search(text)
        if not m:
            continue
        eff_pct = float(m.group(1))
        forms_by_level[lvl] = [SkillHitForm(
            "Split Shot", eff_pct, "additive",
            hit_count=3, shotgun_falloff=_SPLIT_SHOT_FALLOFF, scales_with_projectiles=True)]
    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        shotgun_requires_grant=True,   # base has no Shotgun Effect; Volley grants it
    )


# ── Spell skills ───────────────────────────────────────────────────────────────
# Chain Lightning — Tags: Spell, Lightning, Chain. A spell: it has intrinsic per-level base damage
# and a cast-speed-driven hit rate (no weapon). "Effectiveness of added damage" (136%) scales ADDED
# flat only; the listed base is unscaled (verified in-game — see the implementation plan §1). Per-level
# values live as strings in progression[*].values, so regex them out.
# Phases 2–4 (Numbed, Lucky, supports/shotgun) are layered on separately.
_SPELL_BASE_DMG_RE = re.compile(
    r"Deals\s+([\d.,]+)\s*-\s*([\d.,]+)\s+Spell\s+([A-Za-z]+)\s+Damage", re.IGNORECASE
)
_JUMPS_RE = re.compile(r"\+(\d+)\s+Jump", re.IGNORECASE)


@_register("chain_lightning")
def _resolve_chain_lightning(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {
        entry["level"]: entry["values"]
        for entry in skill_data.get("progression", [])
    }
    base_by_level: dict[int, dict[str, tuple[float, float]]] = {}
    effectiveness = 1.0
    damage_types: list[str] = []
    jumps_base = 2
    for lvl, values in progression.items():
        text = " ".join(str(v) for v in values.values())
        m = _SPELL_BASE_DMG_RE.search(text)
        if m:
            dmin = float(m.group(1).replace(",", ""))
            dmax = float(m.group(2).replace(",", ""))
            dtype = m.group(3).lower()
            base_by_level[lvl] = {dtype: (dmin, dmax)}
            if dtype not in damage_types:
                damage_types.append(dtype)
        eff_val = values.get("Effectiveness of added damage")
        if eff_val:
            em = re.search(r"(\d+(?:\.\d+)?)", str(eff_val))
            if em:
                effectiveness = float(em.group(1)) / 100.0
        jm = _JUMPS_RE.search(str(values.get("Descript", "")))
        if jm:
            jumps_base = int(jm.group(1))

    # One additive hit form per cast. effectiveness_pct=100 is intentional: the spell flat branch in
    # calculate_offense already bakes added-damage effectiveness into the ADDED flat (base stays
    # unscaled), so the shared per-form `eff/100` multiply must be neutral (×1.0).
    forms_by_level = {
        lvl: [SkillHitForm("Chain Lightning", 100.0, "additive")]
        for lvl in base_by_level
    }

    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        is_spell=True,
        base_dmg_by_level=base_by_level,
        base_cast_time=_parse_cast_time(skill_data.get("cast_speed", "")),
        added_dmg_effectiveness=effectiveness,
        damage_types=damage_types,
        jumps_base=jumps_base,
    )


# Lenient base-damage line (the element word is optional — Chromatic Shot prints "Spell Damage" or "Spell Fire damage").
_CHROMA_BASE_RE = re.compile(r"Deals\s+([\d.,]+)\s*-\s*([\d.,]+)\s+Spell(?:\s+[A-Za-z]+)?\s+[Dd]amage", re.I)
_CHROMATIC_ELEMENTS = ["fire", "cold", "lightning"]


@_register("chromatic_shot")
def _resolve_chromatic_shot(skill_data: dict) -> ResolvedSkill:
    """Chromatic Shot — a Spell whose damage is COMPULSORILY converted to one random/rotated element per cast (see
    ResolvedSkill.compulsory_elements). Base damage is type-agnostic; the per-element split + expected average happen
    in offense. Fires 1 + Projectile Quantity projectiles that shotgun one target (falloff 0.70)."""
    max_level = skill_data.get("max_level", 20)
    base_flat: dict[int, tuple[float, float]] = {}
    effectiveness = 1.0
    for entry in skill_data.get("progression", []):
        lvl = entry.get("level")
        values = entry.get("values") or {}
        m = _CHROMA_BASE_RE.search(" ".join(str(v) for v in values.values()))
        if m:
            base_flat[lvl] = (float(m.group(1).replace(",", "")), float(m.group(2).replace(",", "")))
        eff_val = values.get("Effectiveness of added damage")
        if eff_val:
            em = re.search(r"(\d+(?:\.\d+)?)", str(eff_val))
            if em:
                effectiveness = float(em.group(1)) / 100.0
    # Base 3 projectiles (1 + intrinsic "Projectile Quantity +2"); gear/passive +Projectile Quantity adds on top.
    forms = {
        lvl: [SkillHitForm("Chromatic Shot", 100.0, "additive",
                           hit_count=3, shotgun_falloff=0.70, scales_with_projectiles=True)]
        for lvl in base_flat
    }
    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms,
        supported=True,
        is_spell=True,
        base_cast_time=_parse_cast_time(skill_data.get("cast_speed", "")),
        added_dmg_effectiveness=effectiveness,
        damage_types=list(_CHROMATIC_ELEMENTS),
        compulsory_elements=list(_CHROMATIC_ELEMENTS),
        base_flat_by_level=base_flat,
    )


def _parse_cast_time(cast_speed: str) -> float:
    """Parse '0.65 s' → 0.65. Returns 0.0 if unparseable (offense guards against div-by-zero)."""
    m = re.search(r"([\d.]+)", str(cast_speed))
    return float(m.group(1)) if m else 0.0


def _parse_mana_cost(raw: object) -> tuple[float, bool]:
    """Parse the skill's base per-cast Mana Cost → (magnitude, is_percent). '8' → (8.0, False); '15%' → (15.0, True)
    (a % of Max Mana, e.g. Moon Strike / channeled). 0.0 if absent/unparseable. The cost MODEL (multipliers,
    Arcane, Frozen Lotus) lives in engine.skill_cost; this just extracts the base."""
    s = str(raw or "")
    m = re.search(r"[\d.]+", s)
    return (float(m.group(0)) if m else 0.0), ("%" in s)


def _parse_pct(raw: object, default: float = 1.0) -> float:
    """Parse '40%' / '119%' → 0.40 / 1.19. Returns `default` if unparseable."""
    m = re.search(r"([\d.]+)", str(raw or ""))
    return float(m.group(1)) / 100.0 if m else default


# ── Channeled skills ────────────────────────────────────────────────────────────
# Icebound Beam — Tags: Spell, Channeled, Cold, Projectile, Beam. A RESET channeled skill with TWO
# intrinsic base-damage forms that fire at DIFFERENT cadences:
#   • Cold Beam (continuous): fires every use, the spell's per-level base (added-dmg effectiveness 40%).
#   • Icy Blade (reset burst): at max channeled stacks (5), dump all stacks and fire 2 Icy Blades (each its
#     own per-level base, effectiveness 119%); on one target the 1st is full, each subsequent −65% (shotgun).
# Both forms are Cold Spell base — base damage scales per level, so effectiveness scales ADDED flat ONLY (no
# base double-dip). The per-form base + effectiveness are read by offense (SkillHitForm.base_dmg/added_eff).
_ICEBOUND_BEAM_RE = re.compile(
    r"Cold Beam:\s*Deals\s+([\d.,]+)\s*-\s*([\d.,]+)\s+Spell\s+Cold\s+Damage"
    r".*?Icy Blade:\s*Deals\s+([\d.,]+)\s*-\s*([\d.,]+)\s+Spell\s+Cold\s+Damage",
    re.IGNORECASE | re.DOTALL,
)


@_register("icebound_beam")
def _resolve_icebound_beam(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {entry["level"]: entry["values"] for entry in skill_data.get("progression", [])}
    beam_eff = _parse_pct(skill_data.get("effectiveness_of_added_damage"), 0.40)   # Cold Beam: 40%
    forms_by_level: dict[int, list[SkillHitForm]] = {}
    beam_base_by_level: dict[int, dict[str, tuple[float, float]]] = {}
    blade_eff = 1.19
    for lvl, values in progression.items():
        m = _ICEBOUND_BEAM_RE.search(str(values.get("Descript", "")))
        if not m:
            continue
        beam = (float(m.group(1).replace(",", "")), float(m.group(2).replace(",", "")))
        blade = (float(m.group(3).replace(",", "")), float(m.group(4).replace(",", "")))
        blade_eff = _parse_pct(values.get("Effectiveness of added damage"), 1.19)  # Icy Blade: 119%
        beam_base_by_level[lvl] = {"cold": beam}
        forms_by_level[lvl] = [
            # effectiveness_pct=100 keeps the shared per-form eff multiply neutral (spell base is unscaled);
            # the REAL added-damage effectiveness rides added_eff (applied to added flat only).
            SkillHitForm("Cold Beam", 100.0, "additive", base_dmg={"cold": beam},
                         added_eff=beam_eff, channel_role="continuous"),
            # Base 2 blades (1 base projectile + the skill's intrinsic "Projectile Quantity +1"); +Projectile
            # Quantity adds more, all homing/hitting one target with the 65% shotgun falloff.
            SkillHitForm("Icy Blade", 100.0, "additive", base_dmg={"cold": blade},
                         added_eff=blade_eff, channel_role="burst", hit_count=2, shotgun_falloff=0.65,
                         scales_with_projectiles=True),
        ]

    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        is_spell=True,
        # Headline base/effectiveness = the Cold Beam (continuous); the Icy Blade form overrides per-form.
        base_dmg_by_level=beam_base_by_level,
        base_cast_time=_parse_cast_time(skill_data.get("cast_speed", "")),
        added_dmg_effectiveness=beam_eff,
        damage_types=["cold"],
        # "Channels up to 5 stacks" is absent from the SS12 DB → hardcode the cap (max_from_data=False).
        # When the Icy Blade fires, the Cold Beam drops to 1/3 (the channel redistributes beam→blades).
        channeled=ChanneledSpec(max_stacks=5, min_stacks=0, behavior="reset", max_from_data=False,
                                continuous_suppression_when_bursting=1.0 / 3.0),
    )


# Howling Gale — Tags: Spell, Channeled, Physical, Area, Persistent. A REFRESH channeled spell: you channel to
# build Max Channeled Stacks (5), holding at max, which spawns a persistent "Gale" that strikes at its OWN Base
# Attack Frequency (1.5/s × cast speed) — NOT the 0.333 s channel cast rate. Spell base (548-913 Physical at L20)
# is unscaled by effectiveness (125% applies to added flat only). "+21.5% additional damage for every +1 ADDITIONAL
# Max Channeled Stack" (beyond the base 5) → an intrinsic additional scaling off max_channeled_stacks_flat (gear).
# Per-channeled-stack Duration/Area/Movement Speed are non-DPS (informational) for a sustained single-target calc.
_HOWLING_GALE_FREQUENCY = 1.5
_HOWLING_GALE_PER_ADDITIONAL_MAX_STACK = 0.215   # Tyra: counts stacks ABOVE base 5; flag — verify in-game


@_register("howling_gale")
def _resolve_howling_gale(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {entry["level"]: entry["values"] for entry in skill_data.get("progression", [])}
    base_by_level: dict[int, dict[str, tuple[float, float]]] = {}
    effectiveness = 1.25
    damage_types: list[str] = []
    for lvl, values in progression.items():
        m = _SPELL_BASE_DMG_RE.search(" ".join(str(v) for v in values.values()))
        if m:
            dtype = m.group(3).lower()
            base_by_level[lvl] = {dtype: (float(m.group(1).replace(",", "")), float(m.group(2).replace(",", "")))}
            if dtype not in damage_types:
                damage_types.append(dtype)
        eff = values.get("Effectiveness of added damage")
        if eff:
            em = re.search(r"(\d+(?:\.\d+)?)", str(eff))
            if em:
                effectiveness = float(em.group(1)) / 100.0
    forms_by_level = {
        lvl: [SkillHitForm("Howling Gale", 100.0, "additive", channel_role="continuous")]
        for lvl in base_by_level
    }
    return ResolvedSkill(
        skill_id=skill_data["item_id"], name=skill_data["name"], tags=skill_data.get("skill_tags", []),
        max_level=max_level, hit_forms_by_level=forms_by_level, supported=True, is_spell=True,
        base_dmg_by_level=base_by_level, base_cast_time=_parse_cast_time(skill_data.get("cast_speed", "")),
        added_dmg_effectiveness=effectiveness, damage_types=damage_types,
        # REFRESH: hold at max 5; the Gale strikes at attack_frequency 1.5 × cast speed (the damage rate).
        channeled=ChanneledSpec(max_stacks=5, min_stacks=0, behavior="refresh",
                                attack_frequency=_HOWLING_GALE_FREQUENCY),
        # +21.5% additional damage per ADDITIONAL Max Channeled Stack (beyond base 5) = per max_channeled_stacks_flat.
        intrinsic_additional=[IntrinsicAdditional(
            per=_HOWLING_GALE_PER_ADDITIONAL_MAX_STACK, rating_key="max_channeled_stacks_flat",
            rating_source="stat", per_n=1.0)],
    )


_MAIN_STAT_NAMES = frozenset({"strength", "dexterity", "intelligence"})


def _parse_main_stats(raw: object) -> list[str]:
    """Parse a skill's `main_stat` field ("Dexterity, Intelligence", "Intelligence", None) into a
    deduped, lowercased list of attribute names (strength/dexterity/intelligence). Unknown tokens and
    None are dropped. Order preserved for display."""
    if not raw:
        return []
    out: list[str] = []
    for tok in re.split(r"[,/&]| and ", str(raw)):
        name = tok.strip().lower()
        if name in _MAIN_STAT_NAMES and name not in out:
            out.append(name)
    return out


# ── Rosa Holy Domain (trait skill) ──────────────────────────────────────────────
# A trait-granted skill (Rosa High Court Chariot) that deals NO damage but can host supports (Invulnerability /
# Divine Intervention grant the slot). Tagged Area + Channeled (+ Spell) so the appropriate supports gate to it.
# Synthesized in code (NOT in the crawler-generated _skills.json) — server injects it into skills_by_id.
ROSA_HOLY_DOMAIN_ID = "rosa_holy_domain"
ROSA_HOLY_DOMAIN_SKILL = {
    "item_id": ROSA_HOLY_DOMAIN_ID,
    "name": "Holy Domain",
    "skill_type": "active_skill",
    "skill_tags": ["Spell", "Area", "Channeled"],
    "description_lines": ["Trait Skill — deals no damage; supports modify the Holy Domain."],
    "max_level": 1,
    "progression": [],
}


@_register(ROSA_HOLY_DOMAIN_ID)
def _resolve_rosa_holy_domain(skill_data: dict) -> ResolvedSkill:
    return ResolvedSkill(
        skill_id=skill_data.get("item_id", ROSA_HOLY_DOMAIN_ID),
        name=skill_data.get("name", "Holy Domain"),
        tags=skill_data.get("skill_tags", ["Spell", "Area", "Channeled"]),
        max_level=skill_data.get("max_level", 1),
        hit_forms_by_level={},   # deals no damage — only a host for supports
        supported=True,
        is_spell=True,
    )


# Skill-specific modeled mechanics not derivable from the generic ResolvedSkill fields below (e.g. Icebound's
# shotgun/projectile/beam handling, Berserking's buff Skill-Area/stack-cap). Phrases are lowercased substrings.
# NOTE: when a NEW skill is brought to full modeling, add its modeled-mechanic phrases here (or rely on the
# generic ResolvedSkill rules in classify_intrinsic_line for channeled / intrinsic_additional / steep-strike).
_SKILL_MODELED_PHRASES: dict[str, tuple[str, ...]] = {
    "icebound_beam": ("shotgun effect falloff", "projectile quantity", "beam reflection",
                      "fires 1 projectile", "hit the same enemy"),
    "berserking_blade": ("skill area for each stack of buff", "stacks up to"),
    "groundshaker": ("demolisher charge", "fissure", "weapon attack damage",
                     "restoration speed", "skill area when the skill consumes"),
    "split_shot": ("weapon attack damage", "fires 1 projectile", "projectile quantity of this skill",
                   "shotgun effect falloff", "hit the same enemy"),
}


def classify_intrinsic_line(line: str, resolved: ResolvedSkill) -> str | None:
    """Coverage of an active skill's intrinsic tooltip clause:
      'modeled' → the clause names a mechanic the engine ACTUALLY models for this skill (→ green badge).
      None      → not a positively-modeled mechanic; leave the line untouched (its existing keys path decides,
                  so genuinely-unimplemented mechanics honestly stay NYI).
    Strictly gated on ResolvedSkill so it can only green what is truly modeled (generic, low per-season drift)."""
    if not resolved.supported:
        return None
    t = (line or "").lower()
    if resolved.base_steep_strike_chance and "steep strike chance" in t:
        return "modeled"
    if resolved.channeled:
        if "max channeled stack" in t:
            return "modeled"
        if resolved.channeled.attack_frequency and "attack frequency" in t:
            return "modeled"
    if resolved.intrinsic_additional and "additional damage" in t and (
            "for every" in t or "per " in t or "max channeled stack" in t):
        return "modeled"
    # "This skill is affected by <X> Effect" — modeled when an intrinsic additional scales with that effect
    # (e.g. Focused Slash: Fervor Effect scales the per-Fervor-Rating bonus via effect_key).
    if any(ia.effect_key for ia in resolved.intrinsic_additional) and "affected by" in t and "effect" in t:
        return "modeled"
    if resolved.extra_damage_mod_tags and "also appl" in t and "damage" in t:
        return "modeled"
    for phrase in _SKILL_MODELED_PHRASES.get(resolved.skill_id, ()):
        if phrase in t:
            return "modeled"
    return None


def resolve_skill(skill_data: dict) -> ResolvedSkill:
    """Return a ResolvedSkill; supported=False for any skill not in the registry.

    Never falls back to a partial or guessed calculation.
    """
    handler = _REGISTRY.get(skill_data.get("item_id", ""))
    if handler is not None:
        resolved = handler(skill_data)
    else:
        # Unregistered (damage NOT modelled) — but the per-cast COST is data-driven, so still carry the cost fields
        # + the rate primitives (is_spell / cast time) the cost stage needs. supported=False keeps damage at 0.
        _tags = skill_data.get("skill_tags") or skill_data.get("tags") or []
        resolved = ResolvedSkill(
            skill_id=skill_data.get("item_id", ""),
            name=skill_data.get("name", ""),
            tags=list(_tags),
            max_level=0,
            hit_forms_by_level={},
            supported=False,
            is_spell=any(str(t).lower() == "spell" for t in _tags),
            base_cast_time=_parse_cast_time(skill_data.get("cast_speed", "")),
        )
    resolved.main_stat = _parse_main_stats(skill_data.get("main_stat"))
    resolved.mana_cost, resolved.mana_cost_is_percent = _parse_mana_cost(skill_data.get("mana_cost"))
    # Skill-local Arcane: "All Mana costs … converted to Life costs" (Bull's Rage). Detected from the skill's own
    # text (generic) → a per-skill conversion that doesn't leak to other skills like the global Arcane stat would.
    _desc = " ".join(skill_data.get("description_lines") or []) + " " + str(skill_data.get("detailed_description") or "")
    if re.search(r"mana cost.*converted to life cost", _desc, re.I):
        resolved.intrinsic_mana_to_life = 1.0
    return resolved
