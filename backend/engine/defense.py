from __future__ import annotations
from dataclasses import dataclass, field

from engine.models import BuildSource


_BASE_RESIST_CAP     = 60.0
_ABSOLUTE_RESIST_CAP = 90.0


def _elem_resist(source: BuildSource, key: str, max_key: str) -> tuple[float, float]:
    """Fire / Cold / Lightning resistance — elemental_resistance bonus applies.

    Pipeline stores resistance as decimals (0.73 = 73%); multiply by 100 for display units.
    Returns (capped, raw) both in display-unit percentage points.
    """
    raw  = (source.total(key) + source.total("elemental_resistance")) * 100.0
    cap  = min(_BASE_RESIST_CAP + source.total(max_key) * 100.0, _ABSOLUTE_RESIST_CAP)
    return min(raw, cap), raw


def _erosion_resist(source: BuildSource) -> tuple[float, float]:
    """Erosion resistance — elemental_resistance does NOT apply.

    Pipeline stores resistance as decimals (0.73 = 73%); multiply by 100 for display units.
    Returns (capped, raw) both in display-unit percentage points.
    """
    raw  = source.total("erosion_resistance") * 100.0
    cap  = min(_BASE_RESIST_CAP + source.total("erosion_resistance_max_inc") * 100.0, _ABSOLUTE_RESIST_CAP)
    return min(raw, cap), raw


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
    nyi: list[str] = field(default_factory=lambda: ["Effective HP"])


def calculate_defense(source: BuildSource) -> DefenseResult:
    """Read post-loop derived values from source to build the defense summary."""
    fire_c,      fire_r      = _elem_resist(source, "fire_resistance",      "fire_resistance_max_inc")
    cold_c,      cold_r      = _elem_resist(source, "cold_resistance",      "cold_resistance_max_inc")
    lightning_c, lightning_r = _elem_resist(source, "lightning_resistance", "lightning_resistance_max_inc")
    erosion_c,   erosion_r   = _erosion_resist(source)
    return DefenseResult(
        max_life=source.total("max_life"),
        max_mana=source.total("max_mana"),
        max_energy_shield=source.total("max_energy_shield"),
        armor=source.total("armor"),
        evasion=source.total("evasion"),
        fire_resist=fire_c,
        cold_resist=cold_c,
        lightning_resist=lightning_c,
        erosion_resist=erosion_c,
        fire_resist_raw=fire_r,
        cold_resist_raw=cold_r,
        lightning_resist_raw=lightning_r,
        erosion_resist_raw=erosion_r,
        life_flat=source.total("max_life_flat"),
        life_inc=source.total("max_life_inc"),
        life_additional=source.total("max_life_additional"),
        mana_flat=source.total("max_mana_flat"),
        mana_inc=source.total("max_mana_inc"),
        mana_additional=source.total("max_mana_additional"),
        es_flat=source.total("max_energy_shield_flat") + source.total("energy_shield_gear_flat"),
        es_inc=source.total("max_energy_shield_inc") + source.total("energy_shield_gear_inc"),
        es_additional=source.total("max_energy_shield_additional"),
        armor_flat=source.total("armor_flat") + source.total("armor_gear_flat"),
        armor_inc=source.total("armor_inc") + source.total("armor_gear_inc") + source.total("defense_inc"),
        armor_additional=source.total("armor_additional"),
        evasion_flat=source.total("evasion_flat") + source.total("evasion_gear_flat"),
        evasion_inc=source.total("evasion_inc") + source.total("evasion_gear_inc") + source.total("defense_inc"),
        evasion_additional=source.total("evasion_additional"),
    )
