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
    # Block (additive chance, base 0; not consumed by the engine yet — display only, verify in-game).
    attack_block_chance: float = 0.0
    spell_block_chance: float = 0.0
    block_ratio: float = 0.0                  # base 30% + mods, clamped to the upper limit
    block_ratio_upper_limit: float = 0.60     # base 60%, raisable to 80%
    dmg_avoid_chance: float = 0.0
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
    _block_ratio, _block_ratio_upper_limit = block_ratio_value(source)
    return DefenseResult(
        max_life=_max_life,
        max_mana=_max_mana,
        max_energy_shield=source.total("max_energy_shield"),
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
        dmg_avoid_chance=source.total("dmg_avoid_chance"),
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
