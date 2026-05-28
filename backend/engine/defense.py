from __future__ import annotations
from dataclasses import dataclass, field

from engine.models import BuildSource


@dataclass
class DefenseResult:
    max_life: float
    max_mana: float
    max_energy_shield: float
    armor: float
    evasion: float
    fire_resist: float = 0.0      # NYI
    cold_resist: float = 0.0      # NYI
    lightning_resist: float = 0.0 # NYI
    erosion_resist: float = 0.0   # NYI
    nyi: list[str] = field(default_factory=lambda: ["Resistances", "Effective HP"])


def calculate_defense(source: BuildSource) -> DefenseResult:
    """Read post-loop derived values from source to build the defense summary."""
    return DefenseResult(
        max_life=source.total("max_life"),
        max_mana=source.total("max_mana"),
        max_energy_shield=source.total("max_energy_shield"),
        armor=source.total("armor"),
        evasion=source.total("evasion"),
    )
