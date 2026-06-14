"""Build engine-stats payloads the SAME WAY the app does, for golden/integration tests.

Mirrors src/renderer/src/utils/statsPayload.ts `buildEngineStatsPayload` + api/client.ts
`buildCharacterContributions`, so tests drive the real engine with an app-shaped payload:
  - `character` base Life/Mana/Energy contributions (50 + 13/level life, 40 + 5/level mana, …)
  - auto-derived conditions: `level` (character level), `dual_wielding`, `unique_weapon_types`
  - gear in the engine CONTRIBUTION format that buildGearPayload emits (NOT unresolved_texts, which
    silently drops weapon APS/crit/flat — see reference: engine mock builds)
  - `attached_supports` (the slot-1 main skill's supports)

Use make_request(...) and pass it to EngineStatsRequest(**...).
"""
from __future__ import annotations


def character_contributions(level: int, has_prism: bool = False, gear_energy: int = 0) -> list[dict]:
    """Port of buildCharacterContributions: base Life/Mana/Energy by character level."""
    lvl = max(0, min(100, int(level)))
    gained = max(lvl - 1, 0)
    base_life = 50 + 13 * gained
    base_mana = 40 + 5 * gained
    out = [
        {"stat": "max_life_flat", "amount": base_life, "label": "Base", "text": f"+{base_life} Max Life (50 + 13/level)"},
        {"stat": "max_mana_flat", "amount": base_mana, "label": "Base", "text": f"+{base_mana} Max Mana (40 + 5/level)"},
        {"stat": "max_energy_flat", "amount": 4, "label": "Base", "text": "+4 Max Energy"},
    ]
    if gear_energy > 0:
        out.append({"stat": "max_energy_flat", "amount": gear_energy, "label": "Gear", "text": f"+{gear_energy} Max Energy"})
    if lvl > 0:
        out.append({"stat": "max_energy_flat", "amount": lvl, "label": "Levels", "text": f"+{lvl} Max Energy"})
    if has_prism:
        out.append({"stat": "max_energy_flat", "amount": 1000, "label": "Prism", "text": "+1000 Max Energy (Effortless Command)"})
    return out


def _wc(slot: str, name: str, stat: str, val: float) -> dict:
    return {"stat": stat, "display_value": val, "unit": "", "slot": slot, "item_name": name, "text": f"{name}:{stat}"}


def weapon(slot: str, name: str, dmg_min: float, dmg_max: float, aps: float, csr: float) -> dict:
    """A weapon gear item in the engine contribution format buildGearPayload emits."""
    return {"item_name": name, "contributions": [
        _wc(slot, name, "physical_dmg_gear_flat_min", dmg_min),
        _wc(slot, name, "physical_dmg_gear_flat_max", dmg_max),
        _wc(slot, name, "weapon_attack_speed", aps),
        _wc(slot, name, "weapon_crit_rating_flat", csr),
    ]}


# A 1H sword + 1H axe in the two weapon slots → dual wield (attacks need real weapons to deal damage).
DUAL_WEAPONS = [
    weapon("weapon1", "Test Sword", 200, 350, 1.3, 600),
    weapon("weapon2", "Test Axe", 300, 500, 1.1, 600),
]


def make_request(
    skill_id: str,
    level: int,
    attached_supports: list[dict] | None = None,
    *,
    char_level: int = 90,
    gear: list[dict] | None = None,
    dual_wield: bool = True,
    extra_conditions: dict | None = None,
    **extra,
) -> dict:
    """App-shaped engine_stats payload for one main skill. gear defaults to DUAL_WEAPONS."""
    g = DUAL_WEAPONS if gear is None else gear
    cs: dict = {"level": char_level}
    if dual_wield:
        cs["dual_wielding"] = True
        cs["unique_weapon_types"] = 2
    if extra_conditions:
        cs.update(extra_conditions)
    req = dict(
        slots=[None, None, None, None],
        gear=g,
        character=character_contributions(char_level),
        condition_state=cs,
        skills=[{"slot": 1, "skill_id": skill_id, "level": level}],
        main_skill={"skill_id": skill_id, "level": level},
        attached_supports=attached_supports or [],
    )
    req.update(extra)
    return req
