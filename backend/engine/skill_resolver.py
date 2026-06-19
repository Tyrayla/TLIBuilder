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
    # Icebound Beam: ADDITIVE (owner-confirmed — the Icy Blades fire while the beam is still going).
    burst_replaces_continuous: bool = False
    # RESET only: when the burst form actually fires (projectile_count ≥ 1), the CONTINUOUS form's damage is
    # suppressed to this fraction (the channel "redistributes" beam damage into the blades). 1.0 = no
    # suppression. Icebound Beam: 1/3 — validated in-game (beam 113 solo → ~38 steady-state once blades fire;
    # 0/1/2/4/6-projectile recounts all fit beam×(1/3) + additive blades to within ~2%).
    continuous_suppression_when_bursting: float = 1.0


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
    jumps_base: int = 0                         # base Jumps (Phase 4; unused for hit damage today)
    # Main attribute(s) for this skill, lowercased (e.g. ["dexterity", "intelligence"]). Each point of
    # a main-stat attribute grants +0.5% damage to this skill; multi-main-stat skills SUM the attribute
    # totals before applying. Source: TLI Help DB (Strength/Dexterity/Intelligence). Parsed in
    # resolve_skill from the skill's `main_stat` field; consumed by calculate_offense.
    main_stat: list[str] = field(default_factory=list)


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


def _parse_cast_time(cast_speed: str) -> float:
    """Parse '0.65 s' → 0.65. Returns 0.0 if unparseable (offense guards against div-by-zero)."""
    m = re.search(r"([\d.]+)", str(cast_speed))
    return float(m.group(1)) if m else 0.0


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


def resolve_skill(skill_data: dict) -> ResolvedSkill:
    """Return a ResolvedSkill; supported=False for any skill not in the registry.

    Never falls back to a partial or guessed calculation.
    """
    handler = _REGISTRY.get(skill_data.get("item_id", ""))
    if handler is None:
        return ResolvedSkill(
            skill_id=skill_data.get("item_id", ""),
            name=skill_data.get("name", ""),
            tags=[],
            max_level=0,
            hit_forms_by_level={},
            supported=False,
        )
    resolved = handler(skill_data)
    resolved.main_stat = _parse_main_stats(skill_data.get("main_stat"))
    return resolved
