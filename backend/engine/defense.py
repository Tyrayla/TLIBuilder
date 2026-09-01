from __future__ import annotations
from dataclasses import dataclass, field

from engine.models import BuildSource
from engine.derive import _additional_pool_factor


_BASE_RESIST_CAP     = 60.0
_ABSOLUTE_RESIST_CAP = 90.0

# The "calc target" the player's mitigation/evade is shown against. Both numbers describe the same
# high-level enemy (the in-game training dummy): they reproduce the Help-DB examples (armor 49,147 → 66.2%
# physical mitigation; evasion 3,731 → 16.6% attack evade). Tunable by target level later.
_TARGET_LEVEL        = 90        # armor formula uses min(level, 90)
_ENEMY_ACCURACY      = 630.0     # evade formula (within the documented 130–680 range)
_MAX_ARMOR_MITIGATION = 0.80
_MAX_EVADE_CHANCE     = 0.75
# Only 60% of armor applies to non-physical damage by default, raised by "Armor Effective Rate for
# Non-Physical Damage" (armor_effective_rate_non_physical_inc).
_BASE_NONPHYS_ARMOR_RATE = 0.60

# Block Ratio (the fraction of damage absorbed on a Block). Base 30% for every character, clamped to the
# Block Ratio Upper Limit (base 60%, raisable to 80% via block_ratio_upper_limit_flat — Rosa Invulnerability).
_BASE_BLOCK_RATIO = 0.30
_BASE_BLOCK_RATIO_UPPER_LIMIT = 0.60
_MAX_BLOCK_RATIO_UPPER_LIMIT = 0.80

# Chance to Avoid Damage. Source: TLI Help Database — "Chance to Avoid Damage" (0% base, hard-capped at 60%,
# rolled independently per damage type) and "Blur" (Six Gods' Blessing: each Blur Rating grants 0.25% Chance to
# Avoid Damage, scaled by Blur Effect; Max Blur Rating 100 → 25% at +0% effect). Modeled at max rating (the
# full-uptime planner assumption — real-uptime rating decay is a later refinement). needs-verification.
_MAX_DMG_AVOID_CHANCE = 0.60
_BLUR_MAX_RATING = 100.0
_BLUR_AVOID_PER_RATING = 0.0025


def _blur_avoid_chance(source: BuildSource) -> float:
    """Blur's Chance to Avoid Damage: 100 rating × 0.25% × (1 + Blur Effect), applied only while Blur is active.
    Blur Effect (blur_effect_inc) is read unconditionally so it registers as a consumed stat regardless of the
    active gate (mirrors the consumable-universe self-record note in this module)."""
    effect = 1.0 + source.total("blur_effect_inc")
    if not (getattr(source, "condition_state", None) or {}).get("blur_active"):
        return 0.0
    return _BLUR_MAX_RATING * _BLUR_AVOID_PER_RATING * effect


# Barrier (Six Gods' Blessing). Source: TLI Help Database — "Barrier": absorbs Hit/Secondary/Reflected damage
# equal to 20% of (Max Life + Max Energy Shield) at a base absorption rate of 50%. Barrier Shield scales the pool
# (increased + additional); Barrier Absorption Rate scales the rate (clamped to 100% — a barrier can't absorb more
# than a full hit). Modeled at full strength while active; how the pool absorbs an incoming hit is WS3. needs-verification.
_BARRIER_POOL_PCT = 0.20
_BASE_BARRIER_ABSORPTION_RATE = 0.50


def _barrier(source: BuildSource, max_life: float, max_es: float) -> tuple[float, float, bool]:
    """(barrier_shield, absorption_rate, active). The barrier stats are read unconditionally so they register as
    consumed regardless of the active gate; `active` (barrier_active condition) gates the display only."""
    shield = (_BARRIER_POOL_PCT * (max_life + max_es)
              * (1.0 + source.total("barrier_shield_inc"))
              * _additional_pool_factor(source, ["barrier_shield_additional"]))
    rate = min(_BASE_BARRIER_ABSORPTION_RATE * (1.0 + source.total("barrier_absorption_rate_inc")), 1.0)
    active = bool((getattr(source, "condition_state", None) or {}).get("barrier_active"))
    return shield, rate, active


def block_ratio_value(source: BuildSource) -> tuple[float, float]:
    """(block_ratio, upper_limit) — base 30% + Σ block_ratio_inc, clamped to the Upper Limit (base 60% +
    block_ratio_upper_limit_flat, hard-capped at 80%). Shared by defense (display) and the High Court Chariot
    trait module (per-1%-Block-Ratio No Guard / Murderous Intent scaling) so both read the same value."""
    upper_limit = min(_BASE_BLOCK_RATIO_UPPER_LIMIT + source.total("block_ratio_upper_limit_flat"),
                      _MAX_BLOCK_RATIO_UPPER_LIMIT)
    block_ratio = min(_BASE_BLOCK_RATIO + source.total("block_ratio_inc"), upper_limit)
    return block_ratio, upper_limit


def _armor_mitigation(armor: float) -> float:
    """Physical damage reduction from armor (Help DB): armor / (0.9·armor + 3000 + 300·min(level,90)),
    capped at 80%."""
    if armor <= 0:
        return 0.0
    denom = 0.9 * armor + 3000.0 + 300.0 * min(_TARGET_LEVEL, 90)
    return min(armor / denom, _MAX_ARMOR_MITIGATION)


def _evade_chance(evasion: float) -> float:
    """Evade chance (Help DB): 1 − (acc·1.15)/(acc + 0.5·evasion^0.75), capped at 75%."""
    if evasion <= 0:
        return 0.0
    chance = 1.0 - (_ENEMY_ACCURACY * 1.15) / (_ENEMY_ACCURACY + 0.5 * (evasion ** 0.75))
    return max(0.0, min(chance, _MAX_EVADE_CHANCE))


def _elem_resist(source: BuildSource, key: str, max_key: str) -> tuple[float, float]:
    """Fire / Cold / Lightning resistance — elemental_resistance bonus applies.

    Pipeline stores resistance as decimals (0.73 = 73%); multiply by 100 for display units.
    Returns (capped, raw) both in display-unit percentage points.
    """
    raw  = (source.total(key) + source.total("elemental_resistance")) * 100.0
    # Max cap = 60% base + this element's own max-inc + the aggregate Max Elemental Resistance (Fire/Cold/Lightning
    # only — Tenacity Dew; Erosion has its own cap and is excluded), clamped to the absolute ceiling.
    cap  = min(_BASE_RESIST_CAP + (source.total(max_key)
                                   + source.total("max_elemental_resistance_inc")) * 100.0, _ABSOLUTE_RESIST_CAP)
    return min(raw, cap), raw, cap


def _erosion_resist(source: BuildSource) -> tuple[float, float]:
    """Erosion resistance — elemental_resistance does NOT apply.

    Pipeline stores resistance as decimals (0.73 = 73%); multiply by 100 for display units.
    Returns (capped, raw) both in display-unit percentage points.
    """
    raw  = source.total("erosion_resistance") * 100.0
    cap  = min(_BASE_RESIST_CAP + source.total("erosion_resistance_max_inc") * 100.0, _ABSOLUTE_RESIST_CAP)
    return min(raw, cap), raw, cap


@dataclass
class DefenseResult:
    max_life: float
    max_mana: float
    max_energy_shield: float
    armor: float
    evasion: float
    fire_resist: float = 0.0
    cold_resist: float = 0.0
    lightning_resist: float = 0.0
    erosion_resist: float = 0.0
    fire_resist_raw: float = 0.0
    cold_resist_raw: float = 0.0
    lightning_resist_raw: float = 0.0
    erosion_resist_raw: float = 0.0
    # Maximum resistance per type (the cap): 60% base + max-res sources, clamped to the 90% absolute ceiling.
    fire_resist_max: float = 60.0
    cold_resist_max: float = 60.0
    lightning_resist_max: float = 60.0
    erosion_resist_max: float = 60.0
    # Mana / Life sealing & reservation (from engine.utility.apply_reservation; defaults = full pools when
    # nothing seals, so existing no-sealer builds are unchanged).
    sealed_mana: float = 0.0
    unsealed_mana: float = 0.0          # = max_mana − sealed_mana (the usable pool)
    sealed_life: float = 0.0
    unsealed_life: float = 0.0          # = max_life − sealed_life (the usable/effective life pool)
    sealed_mana_compensation: float = 0.0
    insufficient_mana: bool = False
    insufficient_life: bool = False
    # Component breakdown for the stats screen
    life_flat: float = 0.0
    life_inc: float = 0.0
    life_additional: float = 0.0
    mana_flat: float = 0.0
    mana_inc: float = 0.0
    mana_additional: float = 0.0
    es_flat: float = 0.0
    es_inc: float = 0.0
    es_additional: float = 0.0
    armor_flat: float = 0.0
    armor_inc: float = 0.0
    armor_additional: float = 0.0
    evasion_flat: float = 0.0
    evasion_inc: float = 0.0
    evasion_additional: float = 0.0
    # Armour → damage mitigation % (fractions) against the calc target. Non-physical applies only 60% of
    # armour by default, raised by armor_effective_rate_non_physical_inc.
    armor_phys_mitigation: float = 0.0
    armor_nonphys_mitigation: float = 0.0
    # Evasion → evade chance (fractions). Spell evade uses 60% of evasion (spell reduces evasion by 40%).
    attack_evade_chance: float = 0.0
    spell_evade_chance: float = 0.0
    # Block (additive chance, base 0). Consumed by calculate_incoming for the EHP calc (expected reduction =
    # block chance × block ratio); the block ratio/upper-limit still awaits in-game verification.
    attack_block_chance: float = 0.0
    spell_block_chance: float = 0.0
    block_ratio: float = 0.0                  # base 30% + mods, clamped to the upper limit
    block_ratio_upper_limit: float = 0.60     # base 60%, raisable to 80%
    # Chance to Avoid Damage: the final value AFTER the 60% cap. dmg_avoid_blur is Blur's contribution (broken
    # out so the UI can attribute it), before the cap is applied to the sum with the gear/affix pool.
    dmg_avoid_chance: float = 0.0
    dmg_avoid_blur: float = 0.0
    # Barrier (Six Gods' Blessing) — the absorb pool = 20% of (Max Life + Max ES) × Barrier Shield, at a 50% ×
    # Barrier Absorption Rate rate. `barrier_active` gates the display (its own panel appears only when on).
    barrier_shield: float = 0.0
    barrier_absorption_rate: float = 0.0
    barrier_active: bool = False
    nyi: list[str] = field(default_factory=lambda: ["Effective HP"])


def calculate_defense(source: BuildSource, reservation: dict | None = None) -> DefenseResult:
    """Read post-loop derived values from source to build the defense summary. `reservation` (from
    engine.utility.apply_reservation) supplies the sealed/unsealed mana & life pools; absent → full pools."""
    _r = reservation or {}
    fire_c,      fire_r,      fire_m      = _elem_resist(source, "fire_resistance",      "fire_resistance_max_inc")
    cold_c,      cold_r,      cold_m      = _elem_resist(source, "cold_resistance",      "cold_resistance_max_inc")
    lightning_c, lightning_r, lightning_m = _elem_resist(source, "lightning_resistance", "lightning_resistance_max_inc")
    erosion_c,   erosion_r,   erosion_m   = _erosion_resist(source)
    armor = source.total("armor")
    evasion = source.total("evasion")
    nonphys_rate = _BASE_NONPHYS_ARMOR_RATE + source.total("armor_effective_rate_non_physical_inc")
    _max_mana = source.total("max_mana")
    _max_life = source.total("max_life")
    _max_es = source.total("max_energy_shield")
    _block_ratio, _block_ratio_upper_limit = block_ratio_value(source)
    _barrier_shield, _barrier_rate, _barrier_active = _barrier(source, _max_life, _max_es)
    _blur_avoid = _blur_avoid_chance(source)
    return DefenseResult(
        max_life=_max_life,
        max_mana=_max_mana,
        max_energy_shield=_max_es,
        barrier_shield=_barrier_shield,
        barrier_absorption_rate=_barrier_rate,
        barrier_active=_barrier_active,
        sealed_mana=_r.get("sealed_mana", 0.0),
        unsealed_mana=_r.get("unsealed_mana", _max_mana),
        sealed_life=_r.get("sealed_life", 0.0),
        unsealed_life=_r.get("unsealed_life", _max_life),
        sealed_mana_compensation=_r.get("sealed_mana_compensation", 0.0),
        insufficient_mana=_r.get("insufficient_mana", False),
        insufficient_life=_r.get("insufficient_life", False),
        armor=armor,
        evasion=evasion,
        armor_phys_mitigation=_armor_mitigation(armor),
        armor_nonphys_mitigation=_armor_mitigation(armor * nonphys_rate),
        attack_evade_chance=_evade_chance(evasion),
        spell_evade_chance=_evade_chance(evasion * 0.6),
        attack_block_chance=source.total("attack_block_chance_inc"),
        spell_block_chance=source.total("spell_block_chance_inc"),
        block_ratio=_block_ratio,
        block_ratio_upper_limit=_block_ratio_upper_limit,
        dmg_avoid_chance=min(source.total("dmg_avoid_chance") + _blur_avoid, _MAX_DMG_AVOID_CHANCE),
        dmg_avoid_blur=_blur_avoid,
        fire_resist=fire_c,
        cold_resist=cold_c,
        lightning_resist=lightning_c,
        erosion_resist=erosion_c,
        fire_resist_raw=fire_r,
        cold_resist_raw=cold_r,
        lightning_resist_raw=lightning_r,
        erosion_resist_raw=erosion_r,
        fire_resist_max=fire_m,
        cold_resist_max=cold_m,
        lightning_resist_max=lightning_m,
        erosion_resist_max=erosion_m,
        life_flat=source.total("max_life_flat"),
        life_inc=source.total("max_life_inc"),
        # Additional pools multiply per source (see derive._additional_pool_factor); report as the net additional
        # amount (product − 1) so the display's ×(1 + amount) shows the true Π(1+x), not the sum.
        life_additional=_additional_pool_factor(source, ["max_life_additional"]) - 1.0,
        mana_flat=source.total("max_mana_flat"),
        mana_inc=source.total("max_mana_inc"),
        mana_additional=_additional_pool_factor(source, ["max_mana_additional"]) - 1.0,
        es_flat=source.total("max_energy_shield_flat") + source.total("energy_shield_gear_flat"),
        es_inc=source.total("max_energy_shield_inc") + source.total("energy_shield_gear_inc"),
        es_additional=_additional_pool_factor(source, ["max_energy_shield_additional"]) - 1.0,
        armor_flat=source.total("armor_flat") + source.total("armor_gear_flat"),
        armor_inc=source.total("armor_inc") + source.total("armor_gear_inc") + source.total("defense_inc"),
        armor_additional=_additional_pool_factor(source, ["armor_additional"]) - 1.0,
        evasion_flat=source.total("evasion_flat") + source.total("evasion_gear_flat"),
        evasion_inc=source.total("evasion_inc") + source.total("evasion_gear_inc") + source.total("defense_inc"),
        evasion_additional=_additional_pool_factor(source, ["evasion_additional"]) - 1.0,
    )


# ── Incoming damage → Max Hit / EHP (WS3) ───────────────────────────────────────────────────────────────────
# Per-type mitigation of the selected enemy skill's damage (source.enemy_config), producing a Max-Hit and an EHP
# figure per damage type. All magnitudes come from calculate_defense's already-computed values. The mitigation
# ORDER is needs-verification (the standard ARPG order); the per-formula math is Help-DB sourced.
_INCOMING_TYPES = ("physical", "fire", "cold", "lightning", "erosion")
_INCOMING_SHORT = {"physical": "phys", "fire": "fire", "cold": "cold", "lightning": "lightning", "erosion": "erosion"}


def _dmg_taken_factor(source: BuildSource, dtype: str, is_dot: bool) -> float:
    """(1 + net damage-taken-additional) for this type + delivery. Sums the universal pool + the type-scoped pool
    (physical / elemental — fire/cold/lightning; Erosion has no typed pool) + the hit-or-DoT pool. Reductions
    (e.g. Tenacity) are negative and lower incoming; increases raise it. Clamped so the factor never goes below 0."""
    net = source.total("dmg_taken_additional")
    if dtype == "physical":
        net += source.total("physical_dmg_taken_additional")
    elif dtype in ("fire", "cold", "lightning"):
        net += source.total("elemental_dmg_taken_additional")
    net += source.total("dot_dmg_taken_additional") if is_dot else source.total("hit_dmg_taken_additional")
    return max(0.0, 1.0 + net)


def _incoming_taken_fraction(source: BuildSource, defense: DefenseResult, dtype: str, is_dot: bool) -> float:
    """Fraction of a raw incoming hit/DoT of this type that lands after the always-on layers: armour (hit only;
    physical rate vs the reduced non-physical rate), resistance (physical has none), and the damage-taken pools.
    DoT skips armour. Damage-taken-as conversions are NOT yet applied (order-sensitive — a labeled follow-up)."""
    taken = 1.0
    if not is_dot:
        armour_mit = defense.armor_phys_mitigation if dtype == "physical" else defense.armor_nonphys_mitigation
        taken *= (1.0 - armour_mit)
    resist_pct = {"physical": 0.0, "fire": defense.fire_resist, "cold": defense.cold_resist,
                  "lightning": defense.lightning_resist, "erosion": defense.erosion_resist}[dtype]
    taken *= (1.0 - resist_pct / 100.0)
    taken *= _dmg_taken_factor(source, dtype, is_dot)
    return max(0.0, taken)


def _taken_as_fracs(source: BuildSource) -> dict[str, dict[str, float]]:
    """{src: {dst: frac}} — 'Converts N% of <src> Damage Taken to <dst> Damage' (`{src}_taken_as_{dst}_inc`,
    engine/mod_parser.py's generic damage-taken-conversion fallback covers any src/dst pair, not just the
    stat.py-enumerated ones). Capped to ≤100% per source, redistributed by weight when over — mirrors the
    outgoing-conversion cap rule (offense.py::_conversion_fracs) since no in-game statement of the incoming
    cap/normalization rule exists yet. needs-verification."""
    fracs: dict[str, dict[str, float]] = {}
    for s in _INCOMING_TYPES:
        raw = {d: max(0.0, source.total(f"{s}_taken_as_{d}_inc")) for d in _INCOMING_TYPES if d != s}
        tot = sum(raw.values())
        if tot > 1.0:
            raw = {d: v / tot for d, v in raw.items()}
        fracs[s] = {d: v for d, v in raw.items() if v > 1e-12}
    return fracs


def _incoming_taken_fraction_converted(source: BuildSource, defense: DefenseResult,
                                        taken_as: dict[str, dict[str, float]], src_type: str, is_dot: bool) -> float:
    """Weighted-average taken-fraction for `src_type` after splitting through the damage-taken-as conversion:
    the unconverted remainder keeps `src_type`'s own armour/resistance/damage-taken, each converted slice
    picks up its LANDING type's — a physical hit converted to fire uses fire's resistance and the reduced
    non-physical armour rate, matching the 'conversion before type-specific mitigation' ordering. Applied to
    both Hit and DoT with the SAME fractions — no DoT-scoped `_taken_as_` stat exists to distinguish them,
    so this is a deliberate needs-verification assumption (surfaced in calculate_incoming's nyi list), not a
    silent claim that DoTs convert identically to hits."""
    fracs = taken_as.get(src_type, {})
    stay = 1.0 - sum(fracs.values())
    total = 0.0
    if stay > 1e-12:
        total += stay * _incoming_taken_fraction(source, defense, src_type, is_dot)
    for dst, frac in fracs.items():
        total += frac * _incoming_taken_fraction(source, defense, dst, is_dot)
    return max(0.0, total)


def _barrier_capacity(pool: float, barrier_shield: float, absorption_rate: float, active: bool) -> float:
    """Max post-mitigation single-hit damage `x` survivable given usable Life+ES `pool` (P), Barrier capacity
    `barrier_shield` (B) and `absorption_rate` (r): Barrier absorbs min(r·x, B), the remainder x − min(r·x, B)
    must fit in P. Piecewise (owner-specified): non-exhausted case x = P/(1−r), valid iff r·x ≤ B; exhausted
    case x = P + B, valid iff r·x > B. Does NOT assume B·r is the barrier's effective pool. Inactive/no-barrier
    reduces to the plain pool (P). Barrier's placement in the mitigation order (i.e. that `x` is post armour/
    resistance/damage-taken, pre-Life/ES) is assumed, unverified — see barrier.json notes."""
    if not active or barrier_shield <= 0.0:
        return pool
    r = min(max(absorption_rate, 0.0), 1.0)
    candidates: list[float] = []
    if r < 1.0:
        x_a = pool / (1.0 - r)
        if r * x_a <= barrier_shield + 1e-9:
            candidates.append(x_a)
    x_b = pool + barrier_shield
    if r * x_b > barrier_shield - 1e-9:
        candidates.append(x_b)
    return max(candidates) if candidates else pool


def calculate_incoming(source: BuildSource, defense: DefenseResult) -> dict:
    """Per-type incoming-damage mitigation + Max-Hit / static EHP for the selected enemy skill
    (source.enemy_config). Both are STATIC, scenario-based figures — no repeated-hit simulation, attack-frequency
    assumption, or time-to-death-from-a-boss claim.

    Max Hit = the largest single raw hit of this type survivable, worst case (no evade / avoid / block).
    Static EHP = expected raw-damage capacity for a single equivalent hit, folding in Evasion (attack/spell by
    the skill's kind), Chance to Avoid Damage (per type), and expected Block (chance × ratio) — NOT a
    survival-time prediction. Damage-taken-as conversions (`{src}_taken_as_{dst}_inc`) are applied BEFORE
    type-specific armour/resistance/damage-taken mitigation (see `_incoming_taken_fraction_converted`).

    Barrier (while active) uses the one-hit rate-aware model (`_barrier_capacity`) instead of a simple added
    pool, for Max Hit and static EHP alike — Barrier is NOT applied to DoT rows (its applicability to DoT is
    unverified; excluded by default, see barrier.json). DoT rows: resistance + DoT damage-taken only (no
    armour/block/evade), plus raw incoming DPS, mitigated DPS, a DoT effective pool (usable pool ÷ DoT taken
    fraction), and time-to-death without recovery (usable pool ÷ mitigated DPS) — None (render N/A) when the
    incoming DPS or the mitigated DPS is zero, never a divide-by-zero 0/∞."""
    ec = getattr(source, "enemy_config", None) or {}
    kind = ec.get("kind", "attack")
    dmg = ec.get("damage") or {}
    # unsealed_life already defaults to max_life when nothing seals (and is the reduced pool when life is sealed),
    # so use it directly — a real 0.0 (fully-sealed life) must NOT fall back to full Max Life. DoT pools never
    # include Barrier (excluded by default — see _barrier_capacity's docstring).
    pool = defense.unsealed_life + defense.max_energy_shield
    hit_capacity = _barrier_capacity(pool, defense.barrier_shield, defense.barrier_absorption_rate, defense.barrier_active)
    evade = defense.attack_evade_chance if kind == "attack" else defense.spell_evade_chance
    block_chance = defense.attack_block_chance if kind == "attack" else defense.spell_block_chance
    avoid = defense.dmg_avoid_chance
    ratio = defense.block_ratio
    # EHP survival multiplier from the take-0 / partial-reduce layers (all independent). Applies to hits only.
    ehp_mult = max(1e-9, (1.0 - evade) * (1.0 - avoid) * (1.0 - block_chance * ratio))
    taken_as = _taken_as_fracs(source)
    types: dict = {}
    for t in _INCOMING_TYPES:
        short = _INCOMING_SHORT[t]
        f_hit = _incoming_taken_fraction_converted(source, defense, taken_as, t, is_dot=False)
        f_dot = _incoming_taken_fraction_converted(source, defense, taken_as, t, is_dot=True)
        hit_in = float(dmg.get(f"{short}_hit", 0.0) or 0.0)
        dot_in = float(dmg.get(f"{short}_dot", 0.0) or 0.0)
        mitigated_dot = dot_in * f_dot
        types[t] = {
            "incoming_hit": hit_in,
            "incoming_dot": dot_in,
            "mitigated_hit": hit_in * f_hit,
            "mitigated_dot": mitigated_dot,
            "hit_taken_fraction": f_hit,
            "dot_taken_fraction": f_dot,
            "max_hit": (hit_capacity / f_hit) if f_hit > 0.0 else None,
            "ehp": (hit_capacity / (f_hit * ehp_mult)) if f_hit > 0.0 else None,
            # DoT-only: effective pool (raw-DPS terms) and time-to-death without recovery. None (→ UI "N/A")
            # when there's no incoming DPS or full DoT immunity — never a misleading 0 or infinity.
            # FOLLOW-UP (BACKLOG.md §0h, owner 2026-09-01): time-to-death assumes zero recovery, which
            # understates a heavy-regen build — a DoT is a sustained drain, so it should net against the
            # build's own Life/ES regen (RecoveryResult.net_life_per_sec / net_es_per_sec), not ignore it.
            "dot_effective_pool": (pool / f_dot) if f_dot > 0.0 else None,
            "dot_time_to_death": (pool / mitigated_dot) if mitigated_dot > 0.0 else None,
        }
    return {
        "kind": kind,
        "pool": pool,                 # usable Life + ES only (DoT rows use this; Barrier excluded)
        "hit_capacity": hit_capacity, # Barrier-aware max survivable post-mitigation single hit (Hit rows only)
        "evade_chance": evade,
        "avoid_chance": avoid,
        "block_chance": block_chance,
        "block_ratio": ratio,
        "barrier_active": defense.barrier_active,
        "types": types,
        "nyi": [
            "mitigation order of operations (needs-verification)",
            "damage-taken-as conversion: applied to both Hit and DoT with the same fractions — no DoT-scoped "
            "stat exists to distinguish them (needs-verification)",
            "damage-taken-as conversion cap/redistribution rule when >100% from one source (needs-verification, "
            "modeled after the outgoing-conversion cap)",
            "Barrier: mitigation-order placement (assumed post armour/resistance/damage-taken, pre-Life/ES) and "
            "whether it protects DoT (excluded by default) — both needs-verification",
            "DoT Time to Death assumes zero recovery — should net against the build's own regen instead "
            "(BACKLOG.md §0h, follow-up, not yet implemented)",
        ],
    }
