"""Golden + unit coverage for the structured tooltip builder (engine.tooltip.build_tooltip).

Snapshots one representative skill of EACH type so a change in how any type's tooltip is split / valued /
deduped shows up as a diff. Re-capture deliberately by deleting the fixture. Plus two focused asserts that
lock Tyra-confirmed value rule: a standard-support added-flat line shows a RANGE at level 20, and a
tiered (noble/magnificent) roll line shows the MIDPOINT.

Tooltips don't touch the engine, so these are fast (no engine_stats run).
"""
import json
import os

from engine.tooltip import build_tooltip
from persistence import season_manager
from server import _get_skills_data

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "tooltip_golden")
_SEASON = season_manager.get_active_season()
_SKILLS_BY_ID = _get_skills_data(_SEASON) if _SEASON else {}
_BY_NAME = {s.get("name"): s for s in _SKILLS_BY_ID.values()}

# One representative per skill type (and the special cases: range, midpoint, tier-3 exclusion, junk strip).
_REPRESENTATIVE = [
    "Added Lightning Damage",                       # support_skill — added-flat RANGE
    "Multiple Projectiles",                         # support_skill — % scaling + always-show special line
    "Chain Lightning",                              # active_skill — damage range + "+2 Jumps"
    "Howling Gale",                                 # active_skill (modeled) — detailed_description split + 'modeled' coverage
    "Blazing Incineration",                         # passive_skill — Descript scaling + #skillstone strip
    "Acuteness Focus: Sharpening (Magnificent)",    # magnificent — fixed +20% + (a-b)% MIDPOINT per tier
    "Berserking Blade: Decimate (Noble)",           # noble — universal damage line + threshold midpoint
    "Activation Medium: Boss",                      # activation_medium — tier 3 EXCLUDED
]


def _by_name(name):
    s = _BY_NAME.get(name)
    assert s, f"representative skill not found in active season: {name}"
    return s


def _flat_lines(spec):
    """All resolved display strings (default level) for easy assertions."""
    out = []
    for ln in spec["lines"]:
        if ln["values_by_level"]:
            out.append(ln["values_by_level"].get(spec["default_level"], ""))
        else:
            out.append(ln["text"])
    return out


def test_representatives_present():
    assert _SEASON and _SKILLS_BY_ID, "no active season / skills loaded"


def test_added_lightning_shows_range_at_level_20():
    spec = build_tooltip(_by_name("Added Lightning Damage"))
    line = next(ln for ln in spec["lines"] if ln["values_by_level"])
    shown = line["values_by_level"][20]
    # An added-flat damage spread → full "min - max" range, not a midpoint.
    assert " - " in shown and "Lightning Damage" in shown, shown


def test_magnificent_roll_shows_midpoint():
    spec = build_tooltip(_by_name("Acuteness Focus: Sharpening (Magnificent)"))
    line = next(ln for ln in spec["lines"] if ln["values_by_level"])
    # (28-30)% at tier 1 → midpoint 29, NOT a range.
    assert "29 %" in line["values_by_level"][1], line["values_by_level"]
    assert "(" not in line["values_by_level"][1]


def test_activation_medium_excludes_tier_3():
    spec = build_tooltip(_by_name("Activation Medium: Boss"))
    assert 3 not in spec["available_levels"], spec["available_levels"]


def test_gate_line_not_rendered():
    spec = build_tooltip(_by_name("Added Lightning Damage"))
    assert spec["gate_text"]  # captured in the spec...
    assert not any("Supports" in s for s in _flat_lines(spec))  # ...but never shown as a line


def test_tooltip_goldens():
    os.makedirs(_GOLDEN_DIR, exist_ok=True)
    failures = []
    for name in _REPRESENTATIVE:
        spec = build_tooltip(_by_name(name))
        path = os.path.join(_GOLDEN_DIR, name.replace(":", "").replace(" ", "_").replace("/", "_") + ".json")
        current = json.loads(json.dumps(spec, sort_keys=True))
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2, sort_keys=True, ensure_ascii=False)
            continue  # captured baseline
        golden = json.load(open(path, encoding="utf-8"))
        if current != golden:
            failures.append(name)
    assert not failures, f"tooltip spec changed for {failures} — re-capture (delete fixture) if intended"
