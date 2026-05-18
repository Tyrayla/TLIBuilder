# ── NO MANUAL WORK REQUIRED ───────────────────────────────────────────────────
# Structural dataclass. Every stat provider (gear slot, passive node, core
# talent, base stats) produces a list of these when queried.
# CharacterSheet (models/character_sheet.py) collects and aggregates them.
# ──────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass
from models.stat import Stat


@dataclass
class StatContribution:
    stat:   Stat
    value:  float
    source: str    # human-readable label e.g. "Ranger's Broken Mask", "God of Machines Micro"
