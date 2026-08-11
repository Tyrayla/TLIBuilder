"""Chromatic Shot (chromatic_shot) — a Spell whose element model is SEASON DATA, not code (see
engine.skill_resolver._resolve_chromatic_shot, data-driven per the 2026-07-16 fix). Fired as 3 shotgunning
projectiles, plus its canvas supports Lightchaser + Splendor.

  - SS12: Compulsory Damage Type Conversion — each cast deals ONE random/rotated element (Fire/Cold/Lightning);
    ALL added flat folds into base BEFORE conversion; only the final element's increased/additional apply.
    Tyra-confirmed model: headline = expected average across the three elements; shotgun first 100% + each
    subsequent 30% (falloff 0.70) capped at "shots on target" (default 7, all under Lightchaser/tangle).
  - SS13 ("Afterlight"): the forced-conversion line was deleted upstream and skill_tags changed to
    ['Physical'] — Chromatic Shot became a plain Physical spell, no compulsory split. Verified real
    end-to-end output: 529-881 Spell Physical Damage at max level, total_dps 1778.77, compulsory_breakdown {}.

Since the resolver reads this straight from each season's own data (no `if season ==` branch), the SAME test
run against different season data exercises genuinely different code paths. Most of the tests below are about
the SS12 compulsory-conversion/shotgun-cap mechanics specifically (per their own docstrings) and PIN the active
season to SS12 for the engine_stats round trip below, rather than riding whatever the app's ambient active
season happens to be — so this file doesn't silently change meaning at the next season rollover (see
`_resp`/`_off`'s `season` kwarg). The SS13-physical-rework tests near the bottom pin "SS13" explicitly.

NOTE (2026-07-16, FIXED — was previously a live bug, see `.wolf/buglog.json` id
`chromatic-shot-ss13-hardcoded-forced-elemental-conversion`): the two engine call sites that gate the "shots on
target" shotgun-cap mechanic (`engine/offense.py:2078`, `engine/compute.py:1533`) used to key off
`skill.compulsory_elements` / `compulsory_breakdown` as a proxy for "this is Chromatic Shot" — empty for SS13's
reworked (plain Physical) Chromatic Shot, silently disabling the shots-on-target override, Lightchaser's
homing-forces-all-projectiles, and the `condition_maximums`/`auto_conditions` surfacing under the then-active
SS13 season even though the underlying "3 projectiles shotgun onto one target, user can cap how many land"
mechanic is unrelated to whether the damage is compulsorily converted. Both sites now gate on an explicit
`ResolvedSkill.shots_on_target_cap` delivery flag (set unconditionally at `skill_resolver.py:513` for Chromatic
Shot, independent of season/compulsory-conversion), so the mechanic fires identically under SS12 and SS13 — see
`test_ss13_shotgun_shots_on_target_cap_binds_with_elevated_projectiles` below, which pins SS13 and elevates
`projectile_quantity_flat` so the cap actually binds (the pre-fix regression: cap silently inert, 48.9% DPS
overstatement).
"""
import contextlib

import pytest
from engine.skill_resolver import resolve_skill
from persistence import season_manager
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

LC = "chromatic_shot_lightchaser_magnificent"
SP = "chromatic_shot_splendor_noble"


def _skill_data(season="SS12"):
    d = season_manager.load_skills(season)   # normalized runtime view
    items = d if isinstance(d, list) else d.get("skills") or d.get("items") or []
    return next(x for x in items if x.get("item_id") == "chromatic_shot")


def _flat_item(name, pairs):
    """A gear item injecting arbitrary stat contributions (e.g. added spell flat, increased damage)."""
    return {"item_name": name, "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": name, "text": f"{name}:{k}"}
        for k, v in pairs]}


@contextlib.contextmanager
def _pinned_season(name):
    """Temporarily set the ACTIVE season for the engine_stats round trip below, restoring whatever was active
    on exit (even on failure). `resolve_skill` reads compulsory-vs-physical straight off each season's own
    skill data — see the module docstring — so a test that goes through the live endpoint (`_resp`/`_off`,
    unlike the direct `resolve_skill(_skill_data(...))` calls) needs this to stay pinned to the season it's
    actually testing rather than whatever the app has active."""
    prev = season_manager.get_active_season()
    season_manager.set_active_season(name)
    try:
        yield
    finally:
        season_manager.set_active_season(prev)


def _resp(gear=None, supports=None, conds=None, season="SS12"):
    with _pinned_season(season):
        req = make_request("chromatic_shot", 20, attached_supports=supports or [], gear=gear or [],
                           extra_conditions=conds or {})
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()


def _off(gear=None, supports=None, conds=None, season="SS12"):
    return _resp(gear=gear, supports=supports, conds=conds, season=season)["offense"]


# ── Resolver ──────────────────────────────────────────────────────────────────
def test_resolver_fields():
    """SS12 real skill data: skill_tags carry Fire/Cold/Lightning AND the raw_text still states the
    "forcibly convert...to a randomly selected type of Elemental Damage" mechanic, so damage_types
    (derived purely from skill_tags) and compulsory_elements (gated on that raw_text) are identical."""
    r = resolve_skill(_skill_data("SS12"))
    assert r.is_spell and r.supported
    assert r.damage_types == ["fire", "cold", "lightning"]
    assert r.compulsory_elements == ["fire", "cold", "lightning"]
    assert r.base_flat_by_level[1] == (8.0, 14.0) and r.base_flat_by_level[20] == (592.0, 1100.0)
    assert r.added_dmg_effectiveness == pytest.approx(1.57)
    assert r.base_cast_time == pytest.approx(0.65) and r.mana_cost == pytest.approx(8.0)
    assert r.main_stat == ["strength", "dexterity", "intelligence"]
    f = r.hit_forms_by_level[20][0]
    assert f.hit_count == 3 and f.shotgun_falloff == pytest.approx(0.70) and f.scales_with_projectiles


# ── Compulsory conversion ───────────────────────────────────────────────────────
def test_expected_is_average_of_three_elements():
    off = _off()
    cb = off["compulsory_breakdown"]
    assert set(cb) == {"fire", "cold", "lightning"}
    # No per-element mods/resist differences → all three identical, headline = that value.
    avgs = [cb[e]["avg_pre_crit"] for e in cb]
    assert max(avgs) == pytest.approx(min(avgs))


def test_all_added_flat_folds_in_regardless_of_type():
    """Added Fire / Cold / Lightning / Physical flat all raise the skill identically (folded before conversion)."""
    base = _off()["total_dps"]
    fire = _off(gear=[_flat_item("R", [("fire_spell_dmg_flat_min", 200), ("fire_spell_dmg_flat_max", 200)])])["total_dps"]
    cold = _off(gear=[_flat_item("R", [("cold_spell_dmg_flat_min", 200), ("cold_spell_dmg_flat_max", 200)])])["total_dps"]
    phys = _off(gear=[_flat_item("R", [("physical_spell_dmg_flat_min", 200), ("physical_spell_dmg_flat_max", 200)])])["total_dps"]
    assert fire > base
    assert fire == pytest.approx(cold) == pytest.approx(phys)   # type-agnostic fold


def test_per_element_uses_only_final_type_increased():
    """+increased Fire Damage raises ONLY the fire element, not cold/lightning."""
    off = _off(gear=[_flat_item("R", [("fire_dmg_inc", 1.0)])])  # +100% increased Fire
    cb = off["compulsory_breakdown"]
    assert cb["fire"]["avg_pre_crit"] > cb["cold"]["avg_pre_crit"]
    assert cb["cold"]["avg_pre_crit"] == pytest.approx(cb["lightning"]["avg_pre_crit"])


# ── Shotgun / shots-on-target ───────────────────────────────────────────────────
def test_shotgun_default_three_projectiles():
    """Base 3 projectiles, shots default 7 → all 3 land → mult 1 + 2×0.30 = 1.6."""
    f = _off()["hit_forms"][0]
    assert f["hits_per_fire"] == 3 and f["shotgun_mult"] == pytest.approx(1.6)


def test_shots_on_target_default_is_all_projectiles():
    """By default ALL fired projectiles land (the field tracks the projectile count): +6 Quantity → 9 fired,
    9 land → 1 + 8×0.30 = 3.4. The auto value + condition max both equal the projectile count."""
    off = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])
    f = off["hit_forms"][0]
    assert off["projectile_count"] == 9 and f["hits_per_fire"] == 9
    assert f["shotgun_mult"] == pytest.approx(1.0 + 8 * 0.30)


def test_shots_on_target_override_caps_the_shotgun():
    """A user-set Projectile Hits below the count caps the shotgun: 9 fired, override 7 land → 1 + 6×0.30."""
    off = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])], conds={"chromatic_shots_on_target": 7})
    f = off["hit_forms"][0]
    assert off["projectile_count"] == 9 and f["hits_per_fire"] == 7
    assert f["shotgun_mult"] == pytest.approx(1.0 + 6 * 0.30)


# ── Lightchaser ──────────────────────────────────────────────────────────────────
def _sup(item_id, rank=5):
    return [{"item_id": item_id, "slot": 1, "level": 20, "rank": rank, "enabled": True}]


def test_lightchaser_raises_dps_and_forces_all_projectiles():
    # User estimates only 4 of 9 land; Lightchaser's homing overrides that → all 9 land, plus its damage bonuses.
    base = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])], conds={"chromatic_shots_on_target": 4})
    lc = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])], conds={"chromatic_shots_on_target": 4}, supports=_sup(LC))
    assert base["hit_forms"][0]["hits_per_fire"] == 4      # user-capped
    assert lc["hit_forms"][0]["hits_per_fire"] == 9        # homing forces all to land
    assert lc["total_dps"] > base["total_dps"]


def test_lightchaser_main_stat_ratio_boost():
    """Lightchaser raises the main-attribute damage ratio ×1.25 (0.5%/pt → 0.625%/pt). With 500 attributes the
    reported bonus goes +250% (×3.5) → +312.5% (×4.125), and the source line then matches the total."""
    attrs = [_flat_item("A", [("dexterity", 500)])]
    base = _off(gear=attrs)
    lc = _off(gear=attrs, supports=_sup(LC))
    assert base["main_stat_damage_bonus"] == pytest.approx(2.5)
    assert lc["main_stat_damage_bonus"] == pytest.approx(3.125)   # 2.5 × 1.25


def test_zero_main_stat_gives_no_ratio_damage():
    """With no attributes the main-stat bonus is 0 even with Lightchaser (the ratio multiplies a 0 bonus)."""
    assert _off()["main_stat_damage_bonus"] == 0.0
    assert _off(supports=_sup(LC))["main_stat_damage_bonus"] == 0.0


def test_per_type_increased_shows_in_breakdown():
    """A +Fire Damage mod surfaces in the Fire column's increased (not cold/lightning) for the breakdown table."""
    off = _off(gear=[_flat_item("R", [("fire_dmg_inc", 0.5)])])
    assert off["type_inc"]["fire"] == pytest.approx(0.5)
    assert off["type_inc"]["cold"] == pytest.approx(0.0) == off["type_inc"]["lightning"]


# ── Tangle cast-speed breakpoints ───────────────────────────────────────────────
def _tangled(cs_inc):
    """Chromatic Shot tangled (Spell Tangle activator) with a given increased-cast-speed gear roll."""
    sup = [{"item_id": "spell_tangle", "slot": 1, "level": 1, "rank": 1, "enabled": True}]
    return _off(supports=sup, gear=[_flat_item("C", [("cast_speed_inc", cs_inc)])])


def test_tangle_cast_rate_hard_rounds_to_tick_breakpoints():
    """A tangle's per-cast rate snaps to whole server ticks: two different cast speeds that land on the same tick
    count produce the SAME effective rate (Tyra-verified 6.04 & 7.44 casts/s → 5 ticks → 6.0/s)."""
    base = 1.0 / 0.65   # chromatic base cast time 0.65s → ~1.538 casts/s before cast speed
    a = _tangled(6.04 / base - 1.0)
    b = _tangled(7.44 / base - 1.0)
    assert a["tangle_cast_ticks"] == 5 and b["tangle_cast_ticks"] == 5
    assert a["skills_per_second"] == pytest.approx(6.0) == b["skills_per_second"]
    # One tick faster requires crossing the boundary: just under 6.0/s sits at 6 ticks → 5.0/s.
    slow = _tangled(5.99 / base - 1.0)
    assert slow["tangle_cast_ticks"] == 6 and slow["skills_per_second"] == pytest.approx(5.0)


def test_untangled_cast_rate_stays_smooth():
    """Without a Tangle activator the cast rate is the smooth (non-breakpoint) value and no tick count is set."""
    base = 1.0 / 0.65
    off = _off(gear=[_flat_item("C", [("cast_speed_inc", 6.04 / base - 1.0)])])
    assert off["tangle_cast_ticks"] == 0
    assert off["skills_per_second"] == pytest.approx(6.04, abs=1e-3)   # smooth, not snapped to 6.0


# ── Splendor ──────────────────────────────────────────────────────────────────
def test_projectile_hits_max_tracks_projectile_count():
    """Projectile Hits (shots-on-target) caps at the build's projectile count — 3 by default, more with
    +Projectile Quantity — not an artificial constant."""
    base = _resp()["condition_maximums"]["chromatic_shots_on_target"]
    more = _resp(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])["condition_maximums"]["chromatic_shots_on_target"]
    assert base == pytest.approx(3.0)
    assert more == pytest.approx(9.0)


def test_splendor_surfaces_auto_conditions_with_source():
    """Splendor's auto-inflicted ailments come back as auto_conditions (so the Config UI can show them
    checked + locked with the source named), including the engine-derived Frostbite Rating of 10."""
    # Without an inflict source the only auto condition is the all-projectiles-land Projectile Hits default.
    none = _resp().get("auto_conditions") or {}
    assert set(none) == {"chromatic_shots_on_target"}
    auto = _resp(supports=_sup(SP))["auto_conditions"]
    ailments = {"enemy_numbed", "enemy_frostbitten", "enemy_ignited", "frostbite_rating", "numbed_stacks"}
    assert ailments <= set(auto)
    assert all(auto[k]["source"] == "Chromatic Shot: Splendor" for k in ailments)
    assert auto["enemy_numbed"]["value"] is True
    assert auto["frostbite_rating"]["value"] == pytest.approx(10.0)
    assert auto["numbed_stacks"]["value"] == pytest.approx(1.0)   # inflicting Numbed applies ≥1 stack


def test_numbed_stacks_zero_opts_out_of_numbed():
    """A user-set numbed_stacks=0 overrides Splendor's inflict: Numbed turns off (dropping the all-three-ailment
    Hit Damage gate → lower DPS), but the auto intent (1) is still reported so the cleared field can restore it."""
    base = _resp(supports=_sup(SP))
    off = _resp(supports=_sup(SP), conds={"numbed_stacks": 0})
    assert "enemy_numbed" not in off["auto_conditions"]            # opted out → not auto-active
    assert off["auto_conditions"]["numbed_stacks"]["value"] == pytest.approx(1.0)  # intent still reported
    assert off["offense"]["total_dps"] < base["offense"]["total_dps"]              # Splendor gate dropped


def test_splendor_auto_inflicts_three_ailments_and_adds_hit_damage():
    base = _off()
    sp = _off(supports=_sup(SP))
    assert sp["total_dps"] > base["total_dps"]                       # universal +20% + ailment vuln + gated hit dmg
    # Splendor's +hit damage is gated on all three ailments, which it auto-applies → per-element differs from base.
    assert sp["compulsory_breakdown"]["cold"]["avg_pre_crit"] > base["compulsory_breakdown"]["cold"]["avg_pre_crit"]


# ── SS13 "Afterlight" rework — plain Physical, no compulsory conversion ────────────────────────────────
# Real season data (not a synthetic payload): SS13 deleted the "forcibly convert...to a randomly selected
# type of Elemental Damage" line and changed skill_tags from ['Cold','Fire','Lightning'] to ['Physical'].
# The resolver is data-driven (no `if season ==` branch — see module docstring), so this is the SAME code
# path as every SS12 test above, just fed SS13's own data.
def test_resolver_fields_ss13_physical_rework():
    r = resolve_skill(_skill_data("SS13"))
    assert r.is_spell and r.supported
    assert r.damage_types == ["physical"]
    assert r.compulsory_elements == []                 # no forced-conversion line in SS13's raw_text
    assert r.base_flat_by_level == {}                   # no type-agnostic pre-conversion pool to fold into
    assert r.base_dmg_by_level[20] == {"physical": (529.0, 881.0)}   # ordinary per-type spell base
    # Cast time / mana are unchanged by the rework (same base skill, different damage model).
    assert r.base_cast_time == pytest.approx(0.65) and r.mana_cost == pytest.approx(8.0)


def test_ss13_end_to_end_physical_no_compulsory_split():
    """Real end-to-end SS13 payload at max level (Tyra-confirmed): straight 529-881 Spell Physical
    Damage, no per-element compulsory breakdown, no forced elemental conversion of added flat."""
    off = _off(season="SS13")
    assert off["compulsory_breakdown"] == {}
    assert off["flat_dmg_min"] == {"physical": 529.0}
    assert off["flat_dmg_max"] == {"physical": 881.0}
    assert off["total_dps"] == pytest.approx(1778.7692307692305)
    assert off["type_inc"] == {"physical": 0}          # only the native type is tracked, not fire/cold/lightning


def test_ss13_shotgun_still_fires_three_projectiles():
    """The shotgun mechanic itself (3 base projectiles, falloff 0.70) is independent of the compulsory-
    conversion rework — the resolver sets it unconditionally — so it still fires under SS13. NOTE: this alone
    does NOT regression-test the shots_on_target_cap fix — 3 <= the default cap of 7 either way, so it passes
    identically whether the gating is applied or not. See the elevated-projectile tests below for that."""
    f = _off(season="SS13")["hit_forms"][0]
    assert f["hits_per_fire"] == 3 and f["shotgun_mult"] == pytest.approx(1.6)


def test_ss13_shots_on_target_default_is_all_projectiles():
    """SS13 mirror of `test_shots_on_target_default_is_all_projectiles`: by default all fired projectiles
    land. +6 Quantity → 9 fired, 9 land."""
    off = _off(season="SS13", gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])
    f = off["hit_forms"][0]
    assert off["projectile_count"] == 9 and f["hits_per_fire"] == 9
    assert f["shotgun_mult"] == pytest.approx(1.0 + 8 * 0.30)


def test_ss13_shots_on_target_cap_binds_with_elevated_projectiles():
    """Regression test for the fix: two engine call sites (`offense.py`, `compute.py`) used to gate the
    shots-on-target cap on `compulsory_elements`/`compulsory_breakdown`, which is EMPTY for SS13's reworked
    Chromatic Shot — so under the old code the cap was silently inert and all 9 fired projectiles landed
    regardless of the user's cap. Real Tyra-measured numbers (lead's brief, 2026-07-16): SS13, +6 Projectile
    Quantity (3 base + 6 = 9 fired), user cap `chromatic_shots_on_target=4` → correct `hits_per_fire=4`,
    `total_dps=2112.29`. Under the pre-fix bug this was `hits_per_fire=9`, `total_dps=3779.88` (48.9%
    overstatement) — this test fails against that old gating and passes against the fixed
    `skill.shots_on_target_cap` flag (season-independent, set unconditionally by the resolver)."""
    off = _off(season="SS13", gear=[_flat_item("R", [("projectile_quantity_flat", 6)])],
               conds={"chromatic_shots_on_target": 4})
    f = off["hit_forms"][0]
    assert off["projectile_count"] == 9 and f["hits_per_fire"] == 4
    assert off["total_dps"] == pytest.approx(2112.2884615384614)


def test_ss13_condition_maximums_and_auto_conditions_restored():
    """SS13 mirror of `test_projectile_hits_max_tracks_projectile_count` + `test_shots_on_target_default_...`'s
    auto-condition assertion: with the old `compulsory_elements`-gated code, SS13's empty compulsory breakdown
    meant `condition_maximums`/`auto_conditions` for `chromatic_shots_on_target` never got surfaced at all.
    Fixed, they surface identically to SS12."""
    r = _resp(season="SS13", gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])
    assert r["condition_maximums"]["chromatic_shots_on_target"] == pytest.approx(9.0)
    assert r["auto_conditions"]["chromatic_shots_on_target"] == {
        "value": 9.0, "source": "Chromatic Shot (all projectiles land)"}


def test_ss13_lightchaser_forces_all_projectiles_despite_user_cap():
    """SS13 mirror of `test_lightchaser_raises_dps_and_forces_all_projectiles`: Lightchaser's homing overrides
    a lower user shots-on-target cap even though SS13 Chromatic Shot has no compulsory conversion — the
    homing-forces-all-projectiles mechanic is gated on the same season-independent `shots_on_target_cap` flag."""
    capped = _off(season="SS13", gear=[_flat_item("R", [("projectile_quantity_flat", 6)])],
                   conds={"chromatic_shots_on_target": 4})
    lc = _off(season="SS13", gear=[_flat_item("R", [("projectile_quantity_flat", 6)])],
              conds={"chromatic_shots_on_target": 4}, supports=_sup(LC))
    assert capped["hit_forms"][0]["hits_per_fire"] == 4      # user-capped
    assert lc["hit_forms"][0]["hits_per_fire"] == 9           # homing forces all to land


# ── Granted Tags feed +<Tag> Skill Level (owner-ruled 2026-08-10) ──────────────────────────────────────
CONDENSED_FIRE_SUP = "chromatic_shot_condensed_fire_noble"


def test_ss13_condensed_granted_tag_enables_element_skill_level():
    """"The supported skill gains the Fire Tag" (Condensed Fire) makes +Fire Skill Level gear apply —
    owner-ruled 2026-08-10. +5 Fire Skill Level at max level 20 → above-max ×1.10^5 on the whole output,
    exactly matching what +5 physical_skill_level (a native tag) does. Off-element levels stay inert."""
    b = _off(season="SS13", supports=_sup(CONDENSED_FIRE_SUP))["total_dps"]
    fire = _off(season="SS13", supports=_sup(CONDENSED_FIRE_SUP),
                gear=[_flat_item("R", [("fire_skill_level", 5)])])["total_dps"]
    cold = _off(season="SS13", supports=_sup(CONDENSED_FIRE_SUP),
                gear=[_flat_item("R", [("cold_skill_level", 5)])])["total_dps"]
    assert fire / b == pytest.approx(1.10 ** 5)
    assert cold == pytest.approx(b)
    # Display parity: the skill-slot summary's effective level reflects the granted tag too.
    r = _resp(season="SS13", supports=_sup(CONDENSED_FIRE_SUP),
              gear=[_flat_item("R", [("fire_skill_level", 5)])])
    slot1 = next(s for s in r["skill_slots"] if s["slot"] == 1)
    assert slot1["effective_level"] == 25


def test_ss13_no_support_fire_skill_level_still_inert():
    """Without the granted tag, +Fire Skill Level stays inert on the plain-Physical SS13 Chromatic Shot."""
    b = _off(season="SS13")["total_dps"]
    fire = _off(season="SS13", gear=[_flat_item("R", [("fire_skill_level", 5)])])["total_dps"]
    assert fire == pytest.approx(b)


def test_moon_strike_damage_only_pseudo_tag_does_not_enable_spell_skill_level():
    """Moon Strike's extra_damage_mod_tags=['spell'] is DAMAGE-POOL-ONLY (its field contract) — it must NOT
    enable spell_skill_level. Pins the boundary of the granted-tag skill-level rule: only add_mod_tags
    (real granted Tags) count, never the damage-mod pseudo-tags."""
    with _pinned_season("SS13"):
        req0 = make_request("moon_strike", 20)
        req1 = make_request("moon_strike", 20, gear=[_flat_item("R", [("spell_skill_level", 5)])])
        r0 = engine_stats(EngineStatsRequest(**req0))
        r1 = engine_stats(EngineStatsRequest(**req1))
        r0 = r0 if isinstance(r0, dict) else r0.model_dump()
        r1 = r1 if isinstance(r1, dict) else r1.model_dump()
    s0 = next(s for s in r0["skill_slots"] if s["slot"] == 1)
    s1 = next(s for s in r1["skill_slots"] if s["slot"] == 1)
    assert s0["effective_level"] == s1["effective_level"] == 20
