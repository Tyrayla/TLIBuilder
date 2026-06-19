"""Generalized "inflicts Numbed" detection across ALL mod sources (talents, gear, slates, custom mods),
not just attached supports.

Numbed stacks are left USER-SET (we don't estimate hit-rate uptime — incorrect is worse than incomplete).
An inflict line's job here is to (a) enable the `enemy_numbed` gate so "vs Numbed enemy" effects work, and
(b) auto-FLOOR `numbed_stacks` to a small baseline so the build isn't silently at 0 — the user can always
raise it. The floor is applied via the existing max-rule (engine.support_mapper.ConditionEffect, mode="max")
through compute._apply_cond_effects, which respects a manually-set value and gates on the build's hit
damage types.

Functional spec (owner-confirmed):
  A  "Inflicts Numbed when dealing Hit Lightning Damage"        -> enable + floor 1 (Lightning hit)
  B  "% chance to inflict 1 stack of Numbed ... on hit"          -> enable + floor 1 (can ramp; user raises)
  C  "Inflicts N additional stack(s) of Numbed"                  -> raises the floor to 1 + N (needs A/B)
  E  "Critical Strikes are guaranteed to inflict Numbed"         -> like A (Lightning hit)
  G  "inflicts ... Numbed based on Elemental Hit Damage"         -> like A, but any Elemental hit
  H  "cannot inflict ... Numbed"                                 -> HARD override: no Numbed at all
  F  threshold "-X% to ... thresholds for inflicting Numbed"     -> not modelled (informational)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from engine.support_mapper import ConditionEffect

# Numbed lines that are NOT an "inflict on hit" source (effect scaling / recently / threshold / the
# Lightning Shadow trait's own internal wording) — excluded so they don't trip the detector.
_EXCLUDE = (
    "numbed effect", "inflicted numbed recently", "thresholds for inflicting",
    "feline figure", "electrify", "for every stack",
)


@dataclass
class NumbedInflict:
    lightning: bool = False   # an A/B/E Lightning-hit inflict source is present
    elemental: bool = False   # a G Elemental-hit inflict source is present
    additional: int = 0       # Σ of C "inflicts N additional stack(s)"
    blocked: bool = False     # H "cannot inflict Numbed" — overrides everything

    @property
    def active(self) -> bool:
        return self.blocked or self.lightning or self.elemental or self.additional > 0

    def matches(self, text: str) -> bool:
        """True if `text` is one of the inflict/​block/​additional lines this scan recognized (so the caller
        can flip its status from NYI to working — never silently dropped, never falsely red)."""
        return _classify(text) is not None

    def condition_effects(self) -> list[ConditionEffect]:
        """Floor + gate effects for compute._apply_cond_effects. H is handled separately (override)."""
        if self.blocked:
            return []
        floor = 1.0 + float(self.additional)
        effs: list[ConditionEffect] = []
        if self.lightning:
            effs.append(ConditionEffect("enemy_numbed", 1.0, "set_true", requires_dtype="lightning"))
            effs.append(ConditionEffect("numbed_stacks", floor, "max", requires_dtype="lightning"))
        if self.elemental:
            effs.append(ConditionEffect("enemy_numbed", 1.0, "set_true", requires_dtype="elemental"))
            effs.append(ConditionEffect("numbed_stacks", floor, "max", requires_dtype="elemental"))
        return effs


def _classify(raw: str) -> str | None:
    """Classify a single mod line -> 'block' | 'additional' | 'lightning' | 'elemental' | None."""
    if not raw:
        return None
    t = raw.lower()
    if "numbed" not in t:
        return None
    if re.search(r"cannot\s+inflict", t) and "numbed" in t:
        return "block"
    if any(x in t for x in _EXCLUDE):
        return None
    if re.search(r"inflicts?\s+\(?\d+(?:\s*[–\-]\s*\d+)?\)?\s+additional\s+stack", t):
        return "additional"
    # Base inflict: an "inflict ... Numbed" with a hit / deal / critical trigger.
    if re.search(r"\binflicts?\b", t) and re.search(r"\bnumbed\b", t) and re.search(r"hit|deal|critical", t):
        return "elemental" if ("elemental" in t and "lightning" not in t) else "lightning"
    return None


def _additional_count(t: str) -> int:
    m = re.search(r"inflicts?\s+\(?(\d+)(?:\s*[–\-]\s*\d+)?\)?\s+additional\s+stack", t.lower())
    return int(m.group(1)) if m else 0


def scan_numbed_inflict(texts) -> NumbedInflict:
    """Aggregate every mod line in the build into a single NumbedInflict summary."""
    out = NumbedInflict()
    for raw in texts:
        kind = _classify(raw)
        if kind == "block":
            out.blocked = True
        elif kind == "additional":
            out.additional += _additional_count(raw)
        elif kind == "lightning":
            out.lightning = True
        elif kind == "elemental":
            out.elemental = True
    return out
