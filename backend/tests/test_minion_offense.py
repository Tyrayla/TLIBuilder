"""Minion DPS engine (Phase A) — regression tests for engine.minion_offense.

Covers the building-block math (calculate_minion_offense → OffenseResult), the cooldown-capped rate, the NYI
gates, the count fold, and — most importantly — (a) that PLAYER stat pools never leak onto minion damage and
(b) that an UNMODELLED minion contributes NO damage through the engine (the registry gate).
"""
import pytest

from engine.models import BuildSource
from engine.minion_offense import (
    calculate_minion_offense, _interp_level_table, _coefficient_at, MINION_MODULES,
    combine_minion_forms, nyi_offense,
)


_BASE_STATS = {
    "constants": {"fire_res": 60, "cold_res": 60, "lightning_res": 60, "erosion_res": 60,
                  "crit_damage": 150, "crit_rating_flat": 500},
    "base_damage_by_level": {"1": 100, "16": 800, "17": 850, "20": 1000},
    "life_by_group": {"magus": {}, "synthetic_troop": {}},
}

_BASE_SKILL = {
    "name": "Blazing Dance",
    "skill_tags": ["Base Skill", "Spell", "Fire", "Area"],
    "base_damage_coefficient": 110.0,
    "effectiveness_of_added_damage": "110%",
    "cast_speed": "0.8 s",
    "cooldown": None,
}
_ULTIMATE = {
    "name": "Molten Rising",
    "skill_tags": ["Ultimate", "Spell", "Fire", "Area"],
    "base_damage_coefficient": 637.0,
    "effectiveness_of_added_damage": "637%",
    "cast_speed": "1.5 s",
    "cooldown": "8 s",
}


def _src_with_minion_mods():
    s = BuildSource()
    s.add("minion_dmg_inc", 1.5)          # +150% (generic minion)
    s.add("minion_fire_dmg_inc", 0.5)     # +50% fire
    s.add("minion_dmg_additional", 0.2)   # +20% additional
    s.add("minion_crit_rating_inc", 1.0)  # 1000 CSR = 10% crit
    s.add("minion_crit_dmg_inc", 0.3)     # x1.8 crit multiplier
    s.add("minion_cast_speed_inc", 0.2)   # +20% cast speed
    return s


def test_base_skill_pipeline_math():
    o = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, level=20, minion_count=1)
    assert o.supported and o.skill_name == "Blazing Dance (Base)"
    assert "Spell" in o.skill_tags
    assert o.type_inc["fire"] == pytest.approx(2.0)     # 1.5 + 0.5
    assert o.generic_inc == pytest.approx(1.5)          # minion_dmg_inc only (generic, all-types)
    assert o.type_add["fire"] == pytest.approx(1.2)     # x(1+0.2)
    fire = o.hit_forms[0].hit_max_by_type["fire"]
    assert fire == pytest.approx(1100 * 3.0 * 1.2)      # base 1100 x (1+2.0) x 1.2 = 3960
    assert o.crit_chance == pytest.approx(0.10)
    assert o.crit_multiplier == pytest.approx(1.8)
    assert o.skills_per_second == pytest.approx(1.5)    # 1/0.8 x 1.2
    assert o.total_dps == pytest.approx(3960 * 1.08 * 1.5)
    assert o.total_dps_vs_target == pytest.approx(o.total_dps * 0.49)  # fire dummy mitigation


def test_ultimate_cooldown_caps_rate():
    o = calculate_minion_offense(_src_with_minion_mods(), _ULTIMATE, _BASE_STATS, level=20)
    assert o.skills_per_second == pytest.approx(0.125)  # 1/8 cooldown caps the cast rate


def test_minion_count_folds_into_totals_via_cast_multiplier():
    one = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20, minion_count=1)
    three = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20, minion_count=3)
    assert three.total_dps == pytest.approx(one.total_dps * 3)
    assert three.cast_multiplier == pytest.approx(3.0)
    # per-form figures stay per-minion (the table reconciles via cast_multiplier)
    assert three.hit_forms[0].dps_vs_target == pytest.approx(one.hit_forms[0].dps_vs_target)


def test_damage_rows_reconcile_single_ability():
    # count=1 → delivery=1.0: the single damage_row must reproduce total_dps_vs_target exactly and sum
    # pct_of_total to 100.
    o = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, level=20, minion_count=1)
    assert len(o.damage_rows) == 1
    assert o.damage_rows[0].dps_vs_target_final == pytest.approx(o.total_dps_vs_target)
    assert o.damage_rows[0].pct_of_total == pytest.approx(100.0, abs=1e-6)
    assert o.target_mitigation_by_type["fire"] * o.enemy_vuln_by_type["fire"] == pytest.approx(
        o.enemy_mult_by_type["fire"])


def test_damage_rows_fold_minion_count_like_cast_multiplier():
    # count folds into the row the same way it folds into total_dps_vs_target (delivery=count).
    three = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20, minion_count=3)
    assert three.damage_rows[0].dps_vs_target_final == pytest.approx(three.total_dps_vs_target)


_ABILITY_A = {"name": "Ability A", "skill_tags": ["Base Skill", "Spell", "Fire", "Area"],
              "base_damage_coefficient": 110.0, "effectiveness_of_added_damage": "110%",
              "cast_speed": "0.8 s", "cooldown": None}
_ABILITY_B = {"name": "Ability B", "skill_tags": ["Base Skill", "Spell", "Fire", "Area"],
              "base_damage_coefficient": 60.0, "effectiveness_of_added_damage": "60%",
              "cast_speed": "1.0 s", "cooldown": None}


def test_combine_minion_forms_merges_two_damage_abilities_without_double_counting_count():
    """combine_minion_forms must only concatenate hit_forms/damage_rows and re-percentage against the COMBINED
    total — minion `count` is folded in ONCE, per-ability, inside calculate_minion_offense (see its
    `cast_multiplier=float(count)`); combine_minion_forms must not re-apply it."""
    src = _src_with_minion_mods()
    a3 = calculate_minion_offense(src, _ABILITY_A, _BASE_STATS, level=20, minion_count=3)
    b3 = calculate_minion_offense(src, _ABILITY_B, _BASE_STATS, level=20, minion_count=3)
    combined = combine_minion_forms("Combo", [a3, b3], count=3)

    assert len(combined.hit_forms) == len(combined.damage_rows) == 2
    # Concatenation only — no re-applied count.
    assert combined.total_dps_vs_target == pytest.approx(a3.total_dps_vs_target + b3.total_dps_vs_target)
    a1 = calculate_minion_offense(src, _ABILITY_A, _BASE_STATS, level=20, minion_count=1)
    assert a3.total_dps_vs_target == pytest.approx(a1.total_dps_vs_target * 3)   # count folds ONCE, per-ability

    # Re-percentage against the COMBINED total (not each ability's own single-ability 100%).
    assert combined.damage_rows[0].dps_vs_target_final == pytest.approx(a3.total_dps_vs_target)
    assert combined.damage_rows[1].dps_vs_target_final == pytest.approx(b3.total_dps_vs_target)
    assert sum(row.pct_of_total for row in combined.damage_rows) == pytest.approx(100.0, abs=1e-6)
    expected_a_pct = a3.total_dps_vs_target / combined.total_dps_vs_target * 100.0
    assert combined.damage_rows[0].pct_of_total == pytest.approx(expected_a_pct)


def test_combine_minion_forms_all_nyi_damage_rows_len_matches_hit_forms():
    """CONFIRMED-DEFECT regression: the all-NYI early return (no damage ability at all) must still carry
    damage_rows 1:1 with hit_forms — combine_minion_forms's own stated invariant, applies unconditionally."""
    n1 = nyi_offense({"name": "Skill A", "skill_tags": []}, 20)
    n2 = nyi_offense({"name": "Skill B", "skill_tags": []}, 20)
    combined = combine_minion_forms("Owner", [n1, n2], count=1)
    assert not combined.supported
    assert len(combined.hit_forms) == 2
    assert len(combined.damage_rows) == len(combined.hit_forms)


def test_player_stats_do_not_leak_into_minions():
    base = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20)
    s = _src_with_minion_mods()
    for k, v in [("dmg_inc", 5.0), ("fire_dmg_inc", 5.0), ("dmg_additional", 2.0), ("crit_rating_inc", 5.0),
                 ("crit_dmg_inc", 3.0), ("cast_speed_inc", 2.0), ("spell_dmg_inc", 5.0), ("elemental_dmg_inc", 5.0)]:
        s.add(k, v)
    polluted = calculate_minion_offense(s, _BASE_SKILL, _BASE_STATS, 20)
    assert polluted.total_dps == pytest.approx(base.total_dps)
    assert polluted.crit_chance == pytest.approx(base.crit_chance)
    assert polluted.skills_per_second == pytest.approx(base.skills_per_second)


def test_nyi_when_base_stats_unfilled():
    empty = {"constants": {}, "base_damage_by_level": {"1": 0, "20": 0}, "life_by_group": {}}
    o = calculate_minion_offense(BuildSource(), _BASE_SKILL, empty, 20)
    assert not o.supported and o.total_dps == 0.0 and o.nyi


def test_nyi_when_no_coefficient():
    buff = {"name": "Blazing Spin", "skill_tags": ["Empower", "Spell", "Fire"],
            "base_damage_coefficient": None, "cast_speed": "0.6 s", "cooldown": "10 s"}
    o = calculate_minion_offense(BuildSource(), buff, _BASE_STATS, 20)
    assert not o.supported


def test_per_level_coefficient_interpolation():
    assert _coefficient_at({"1": 185.0, "20": 278.0}, 20) == pytest.approx(278.0)
    assert _coefficient_at(110.0, 5) == pytest.approx(110.0)
    assert _interp_level_table({"1": 100, "20": 1000}, 16) == pytest.approx(100 + (1000 - 100) * 15 / 19)


def test_growth_stage_thresholds():
    from engine.minion_offense import spirit_magi_growth, growth_stage
    s = BuildSource()
    assert spirit_magi_growth(s) == 100.0 and growth_stage(100) == 1   # base Stage 1
    s.add("spirit_magi_initial_growth_flat", 100)
    assert spirit_magi_growth(s) == 200.0 and growth_stage(200) == 2   # Stage 2
    assert growth_stage(500) == 5 and growth_stage(1000) == 5          # caps at 5


def test_thunder_magus_module_base_enhanced_blend_and_gates():
    """Thunder Magus is modelled as ONE OffenseResult whose hit forms are Base + Enhanced (uptime-split at the
    shared attack rate), Empower's +35% AS folded in, and Empower/Ultimate surfaced as NYI notes (not forms)."""
    import json
    from engine.minion_offense import MINION_MODULES
    from persistence import season_manager
    import engine.minion_effects  # noqa: F401 — register
    assert "summon_thunder_magus" in MINION_MODULES
    owner = next(s for s in json.load(open(
        season_manager._season_dir("SS12") + "/_skills.json", encoding="utf-8"))["skills"]
        if s["item_id"] == "summon_thunder_magus")
    base_stats = season_manager.load_minion_base_stats("SS12")
    handler = MINION_MODULES["summon_thunder_magus"]

    # Empower AS = 35% × 60% uptime (6 s ÷ 10 s) = +21% additional AS. The Empower cast-slot (Thundercloud Surge's
    # 0.6 s cast, ~half effective, on the 10 s cooldown) scales the attack rate by (1 − 0.5·0.6/10) = 0.97.
    base_rate = (1 / 0.8) * (1 + 0.35 * 0.6)
    cast_slot = 1 - 0.5 * (0.6 / 10)                # 0.97

    # Stage 1: 0% Enhanced chance → Enhanced fires 0, Base carries all (× the cast-slot factor).
    r1 = handler(BuildSource(), owner, base_stats, 20, 1)
    assert r1.supported and r1.total_dps > 0
    forms = {f.name.split(" (")[0]: f for f in r1.hit_forms}
    assert forms["Lightning Star"].dps_contribution > 0 and not forms["Lightning Star"].nyi
    assert forms["Lightning Star"].fires_per_sec == pytest.approx(base_rate * cast_slot)
    assert forms["Thunderlight Arrow"].fires_per_sec == 0.0 and forms["Thunderlight Arrow"].dps_contribution == 0.0
    # Empower + Ultimate ARE forms now — visible/selectable in the dropdown, but NYI (0 DPS, carry their reason).
    assert forms["Thundercloud Surge"].nyi and forms["Thundercloud Surge"].dps_contribution == 0.0
    assert forms["Lightning Surge"].nyi and forms["Lightning Surge"].dps_contribution == 0.0
    assert any("Thundercloud Surge" in n for n in forms["Thundercloud Surge"].nyi)   # Empower reason surfaced
    assert any("Lightning Surge" in n for n in forms["Lightning Surge"].nyi)         # Ultimate reason surfaced

    # Stage 2: Growth 200 → +30% Enhanced chance (p=0.30). Base fires at (1−p); Enhanced fires at its RAW chance p
    # PLUS the fast-insert bump p·F·(1−p) → p·(1 + F(1−p)), F=0.90. Both ×cast_slot. Enhanced lands 2 hits/cast.
    src = BuildSource(); src.add("spirit_magi_initial_growth_flat", 100)
    r2 = handler(src, owner, base_stats, 20, 1)
    forms2 = {f.name.split(" (")[0]: f for f in r2.hit_forms}
    p = 0.30
    assert forms2["Lightning Star"].fires_per_sec == pytest.approx(base_rate * (1 - p) * cast_slot)
    assert forms2["Thunderlight Arrow"].fires_per_sec == pytest.approx(base_rate * p * (1 + 0.90 * (1 - p)) * cast_slot)
    assert forms2["Thunderlight Arrow"].hits_per_fire == 2 and forms2["Thunderlight Arrow"].shotgun_mult == pytest.approx(2.0)


def test_spirit_magi_physique_and_skill_area_helpers():
    """Growth (in-game tooltip): +1% Physique per 8 Growth; +10% additional Skill Area per STAGE. Physique also
    picks up the gear/talent `minion_physique_inc` pool."""
    from engine.minion_offense import spirit_magi_physique_inc, spirit_magi_skill_area_inc
    s = BuildSource()
    assert spirit_magi_physique_inc(s, 100) == pytest.approx(0.125)     # 100 ÷ 8 = 12.5% → 0.125
    assert spirit_magi_skill_area_inc(1) == pytest.approx(0.10)         # Stage 1 → +10%
    assert spirit_magi_skill_area_inc(5) == pytest.approx(0.50)         # Stage 5 → +50%
    s2 = BuildSource(); s2.add("minion_physique_inc", 0.10)             # gear Physique stacks on top
    assert spirit_magi_physique_inc(s2, 400) == pytest.approx(0.5 + 0.10)


def test_thunder_magus_surfaces_growth_state_through_module():
    """The combined result carries the Spirit Magus Growth panel state (Growth/Stage/Physique/Skill Area/
    Enhanced chance/Max) for display — none of which (beyond the already-folded stage bonuses) changes hit DPS."""
    import json
    from engine.minion_offense import MINION_MODULES
    from persistence import season_manager
    import engine.minion_effects  # noqa: F401
    owner = next(s for s in json.load(open(
        season_manager._season_dir("SS12") + "/_skills.json", encoding="utf-8"))["skills"]
        if s["item_id"] == "summon_thunder_magus")
    base_stats = season_manager.load_minion_base_stats("SS12")
    r = MINION_MODULES["summon_thunder_magus"](BuildSource(), owner, base_stats, 20, 2)
    assert r.spirit_magi_growth == 100 and r.spirit_magi_stage == 1     # base Growth → Stage 1
    assert r.spirit_magi_physique_inc == pytest.approx(0.125)           # +12.5% Physique from 100 Growth (per 8)
    assert r.skill_area_inc == pytest.approx(0.10)                      # Stage 1 → +10% additional Skill Area
    assert r.spirit_magi_max == 2                                       # the count that fights
    assert r.spirit_magi_enhanced_chance == 0.0                        # Stage 1 → no Enhanced chance yet


def test_thunder_magus_empower_damage_buff_uses_true_uptime():
    """Stage 4+ Empower grants +25% additional damage; at the buff's true 60% uptime (6 s ÷ 10 s) that folds in
    as +15% (0.25 × 0.6), so the minion's generic additional multiplier is ×1.15 (no Stage-5 +50% yet)."""
    import json
    from engine.minion_offense import MINION_MODULES, spirit_magi_growth, growth_stage
    from persistence import season_manager
    import engine.minion_effects  # noqa: F401
    owner = next(s for s in json.load(open(
        season_manager._season_dir("SS12") + "/_skills.json", encoding="utf-8"))["skills"]
        if s["item_id"] == "summon_thunder_magus")
    base_stats = season_manager.load_minion_base_stats("SS12")
    handler = MINION_MODULES["summon_thunder_magus"]
    src = BuildSource(); src.add("spirit_magi_initial_growth_flat", 300)   # Growth 400 → Stage 4 (not 5)
    assert growth_stage(spirit_magi_growth(src)) == 4
    r = handler(src, owner, base_stats, 20, 1)
    assert r.generic_add == pytest.approx(1.15)      # 0.25 × 0.6 uptime = +15% additional damage


def _thunder_owner_and_stats():
    import json
    from persistence import season_manager
    import engine.minion_effects  # noqa: F401
    owner = next(s for s in json.load(open(
        season_manager._season_dir("SS12") + "/_skills.json", encoding="utf-8"))["skills"]
        if s["item_id"] == "summon_thunder_magus")
    return owner, season_manager.load_minion_base_stats("SS12")


def test_thunder_magus_empower_display_matches_form_name():
    """The `minion_empower` display dict must exist AND its `name` must exactly equal the Empower hit_form's
    name (ability_label → 'Thundercloud Surge (Empower)') — the frontend gates the structured Empower panel on
    that match, so a bare skill name would silently fall back to the plain NYI text. Also pins the buff shape."""
    from engine.minion_offense import MINION_MODULES
    owner, base_stats = _thunder_owner_and_stats()
    r = MINION_MODULES["summon_thunder_magus"](BuildSource(), owner, base_stats, 20, 2)
    emp = r.minion_empower
    assert emp is not None, "Thunder Magus must surface a minion_empower display block"
    nyi_form_names = [f.name for f in r.hit_forms if f.nyi]
    assert emp["name"] in nyi_form_names, f"{emp['name']!r} must match a NYI form ({nyi_form_names})"
    assert emp["base_cooldown"] == pytest.approx(10.0) and emp["base_duration"] == pytest.approx(6.0)
    assert emp["uptime"] == pytest.approx(0.60)               # 6 s ÷ 10 s, no CDR / duration mods
    labels = {b["label"]: b for b in emp["buffs"]}
    assert labels["Attack Speed (Euphoria)"]["active"] is True
    assert labels["Attack Speed (Euphoria)"]["value"] == pytest.approx(0.35 * 0.60)   # base × uptime (empEff 1)
    assert labels["Damage (Growth Stage 4+)"]["active"] is False    # Stage 1 → damage buff not yet unlocked


def test_thunder_magus_enhanced_2hit_through_return_always_stronger():
    """Thunderlight Arrow (Enhanced) passes THROUGH the target then tracks back — 2 FULL-damage hits per cast (no
    falloff) at EVERY Growth stage (reverse-engineered + validated in-game 2026-07-06). Its per-hit coefficient
    (189% @20) is below Base (232%), but 2 full hits (~378%) make it always stronger. Stage 3's extra projectile
    adds +5% additional (multi-target arrow), NOT a same-target shotgun."""
    from engine.minion_offense import MINION_MODULES
    owner, base_stats = _thunder_owner_and_stats()
    handler = MINION_MODULES["summon_thunder_magus"]

    # Stage 1: already 2 full hits (through + return), stronger than Base per cast — no shotgun/falloff.
    r1 = handler(BuildSource(), owner, base_stats, 20, 1)
    f1 = {f.name.split(" (")[0]: f for f in r1.hit_forms}
    enh1, base1 = f1["Thunderlight Arrow"], f1["Lightning Star"]
    assert enh1.hits_per_fire == 2 and enh1.shotgun_mult == pytest.approx(2.0)   # 2 hits, each FULL damage
    assert base1.hits_per_fire == 1 and base1.shotgun_mult == pytest.approx(1.0)
    # Per-cast: Enhanced 2×189% vs Base 1×232% → ~1.63× stronger.
    assert enh1.avg_hit_pre_crit * enh1.shotgun_mult == pytest.approx(base1.avg_hit_pre_crit * (189 * 2) / 232, rel=1e-3)

    # Stage 3: +1 projectile → +5% additional on the hit; still exactly 2 single-target hits (not a shotgun).
    s3 = BuildSource(); s3.add("spirit_magi_initial_growth_flat", 200)   # Growth 300 → Stage 3
    enh3 = {f.name.split(" (")[0]: f for f in handler(s3, owner, base_stats, 20, 1).hit_forms}["Thunderlight Arrow"]
    assert enh3.hits_per_fire == 2 and enh3.shotgun_mult == pytest.approx(2.0)
    assert enh3.avg_hit_pre_crit == pytest.approx(enh1.avg_hit_pre_crit * 1.05, rel=1e-3)   # +5% from the +1 proj


def test_thunder_magus_external_projectile_quantity_grants_additional():
    """External minion +Projectile Quantity (multi-proj support on the link / a +Proj weapon shared to the minion)
    grants +5% additional damage EACH to Thunderlight Arrow, but does NOT add single-target hits — it always lands
    exactly 2 (through + return); the extra arrows are multi-target only."""
    from engine.minion_offense import MINION_MODULES
    owner, base_stats = _thunder_owner_and_stats()
    handler = MINION_MODULES["summon_thunder_magus"]

    s0 = BuildSource()                                                  # Stage 1, no external → +0%
    s2 = BuildSource(); s2.add("minion_projectile_quantity_flat", 2)    # +2 external → +5%×2 = +10%
    e0 = [f for f in handler(s0, owner, base_stats, 20, 1).hit_forms if "Thunderlight" in f.name][0]
    e2 = [f for f in handler(s2, owner, base_stats, 20, 1).hit_forms if "Thunderlight" in f.name][0]
    assert e0.hits_per_fire == 2 and e2.hits_per_fire == 2 and e2.shotgun_mult == pytest.approx(2.0)
    assert e2.avg_hit_pre_crit == pytest.approx(e0.avg_hit_pre_crit * 1.10, rel=1e-3)     # +5% × 2 external


def test_thunder_magus_enhanced_dps_matches_ingame_validation():
    """End-to-end lock on the reverse-engineered Enhanced model — 2-hit through+return + p(1−p) fast-insert +
    Empower cast-slot + level-scaled Base coefficient — validated in-game 2026-07-06 (Tyra; magus-only, level 16,
    no gear). Engine vs-target DPS at 0 / 18 / 47 / 100 % Enhanced chance must stay within 2 % of the measured
    202 / 265 / 326 / 320 (the 47 % and 100 % raw measurements 346 / 588 are normalized here by the +6 % / +84 %
    increased minion damage those runs carried). If this drifts, the minion model or its calibration changed."""
    from engine.minion_offense import MINION_MODULES
    owner, base_stats = _thunder_owner_and_stats()
    handler = MINION_MODULES["summon_thunder_magus"]
    for p, tgt in {0.0: 202, 0.18: 265, 0.47: 326, 1.0: 320}.items():
        src = BuildSource()
        if p > 0:
            src.add("spirit_magi_enhanced_skill_chance", p)
        dps = handler(src, owner, base_stats, 16, 1).total_dps_vs_target
        assert dps == pytest.approx(tgt, rel=0.02), f"enhanced={p:.0%}: engine {dps:.1f} vs measured {tgt}"


def test_minion_coefficient_override_precedence():
    """Base-skill coefficient resolution: a crawler per-level TABLE always wins; a bare scalar (crawler only
    captured the max level) falls back to the hand-collected override file (which survives re-imports). Lightning
    Star's crawler value is still the scalar 232, but the SS12 override supplies 221 @16 / 225 @17 / 232 @20."""
    from engine.minion_offense import _resolve_coefficient, _coefficient_overrides
    from persistence import season_manager
    assert "Lightning Star" in _coefficient_overrides(season_manager.get_active_season())
    ls = {"name": "Lightning Star", "base_damage_coefficient": 232.0}   # crawler scalar (unchanged in _skills.json)
    assert _resolve_coefficient(ls, 16) == pytest.approx(221.0)         # override, not the 232 scalar
    assert _resolve_coefficient(ls, 20) == pytest.approx(232.0)
    assert _resolve_coefficient(ls, 19) == pytest.approx(230.5)         # engine interpolates the gap (18↔20)
    # A crawler TABLE takes precedence over any override (never overridden when real data exists).
    tabled = {"name": "Lightning Star", "base_damage_coefficient": {"16": 999.0, "20": 999.0}}
    assert _resolve_coefficient(tabled, 16) == pytest.approx(999.0)
    # An ability with no override + a scalar just uses the scalar.
    assert _resolve_coefficient({"name": "Nonexistent Skill", "base_damage_coefficient": 50.0}, 16) == pytest.approx(50.0)


def test_thunder_magus_empower_uptime_responds_to_minion_cdr_and_duration():
    """Empower uptime = effective duration ÷ effective cooldown (clamped ≤ 1). Generic minion mods drive it:
    Minion Skill Effect Duration lengthens the 6 s buff, Minion Cooldown Recovery Speed shortens the 10 s cd."""
    from engine.minion_offense import MINION_MODULES
    owner, base_stats = _thunder_owner_and_stats()
    handler = MINION_MODULES["summon_thunder_magus"]

    def as_rate(r):   # Stage-1 Base form fires at the full attack rate → exposes the Empower AS uptime + cast-slot.
        return next(f for f in r.hit_forms if "Lightning Star" in f.name).fires_per_sec

    def cast_slot(cd):   # Empower cast-slot: a shorter cooldown (CDR) means more casts → MORE attacking time lost.
        return 1 - 0.5 * (0.6 / cd)

    # No mods → 6/10 = 60% uptime → +35% AS × 0.6 = +21%; cast-slot at cd=10.
    assert as_rate(handler(BuildSource(), owner, base_stats, 20, 1)) == pytest.approx((1 / 0.8) * (1 + 0.35 * 0.6) * cast_slot(10))
    # +20% Skill Effect Duration → 7.2 s ÷ 10 s = 72% uptime; cooldown unchanged so cast-slot unchanged.
    s1 = BuildSource(); s1.add("minion_skill_effect_duration_inc", 0.20)
    assert as_rate(handler(s1, owner, base_stats, 20, 1)) == pytest.approx((1 / 0.8) * (1 + 0.35 * (7.2 / 10)) * cast_slot(10))
    # +50% Duration (9 s) + 25% CDR (10/1.25 = 8 s) → 9/8 > 1 → clamped to 100% uptime → +35% AS full. CDR also
    # SHRINKS the cast-slot (cd 8 → more casts) — exactly why Extended Duration is more DPS-efficient than CDR.
    s2 = BuildSource(); s2.add("minion_skill_effect_duration_inc", 0.50); s2.add("minion_cdr_speed_inc", 0.25)
    assert as_rate(handler(s2, owner, base_stats, 20, 1)) == pytest.approx((1 / 0.8) * 1.35 * cast_slot(8))


def test_player_to_minion_stat_remap():
    """The support→minion remap converts a player stat to its minion-scoped equivalent; keys with no minion
    version fall through unchanged."""
    from engine.minion_offense import to_minion_stat
    assert to_minion_stat("attack_speed_inc") == "minion_attack_speed_inc"
    assert to_minion_stat("cast_speed_inc") == "minion_cast_speed_inc"
    assert to_minion_stat("cdr_speed_inc") == "minion_cdr_speed_inc"
    assert to_minion_stat("skill_effect_duration_inc") == "minion_skill_effect_duration_inc"
    # Added-flat damage carries an attack|spell infix the minion pool lacks — the cat-infix bridge handles it.
    assert to_minion_stat("lightning_attack_dmg_flat_min") == "minion_lightning_dmg_flat_min"
    assert to_minion_stat("physical_spell_dmg_additional") == "minion_physical_dmg_additional"
    assert to_minion_stat("dmg_inc") == "minion_dmg_inc"
    assert to_minion_stat("crit_rating_inc") == "minion_crit_rating_inc"
    assert to_minion_stat("projectile_quantity_flat") == "minion_projectile_quantity_flat"
    assert to_minion_stat("empower_effect_inc") == "empower_effect_inc"      # no minion version → unchanged
    assert to_minion_stat("weapon_attack_speed") == "weapon_attack_speed"    # weapon-only → unchanged


def test_support_on_minion_owner_converts_to_minion_stats_through_engine():
    """A standard support attached to a minion owner's slot is remapped to minion pools — it scales the MINION
    (Added Lightning Damage → minion flat lightning → higher magus DPS) and does NOT leak into the player's pools."""
    from tests.mock_build import make_request
    from server import engine_stats, EngineStatsRequest
    sup = [{"item_id": "added_lightning_damage", "skill_type": "support_skill", "level": 20, "slot": 1}]
    base = engine_stats(EngineStatsRequest(**make_request("summon_thunder_magus", 20)))
    withs = engine_stats(EngineStatsRequest(**make_request("summon_thunder_magus", 20, attached_supports=sup)))
    # Minion DPS rose because the support's Added Lightning Damage converted to the minion flat pool.
    assert withs["minion_offense"]["summon_thunder_magus"]["total_dps"] > base["minion_offense"]["summon_thunder_magus"]["total_dps"]
    # No leak: the player's own lightning flat pool never received the support's damage.
    assert withs.get("stats", {}).get("lightning_dmg_flat_min", {}).get("total", 0) == 0


def test_origin_of_thunder_buffs_summoner_through_engine():
    """Slotting a Thunder Magus auto-grants the summoner Origin of Thunder: +6% additional Cast Speed + level-
    scaled additional damage (7.25% at L20), emitted globally by the aggregator."""
    from tests.mock_build import make_request
    from server import engine_stats, EngineStatsRequest
    res = engine_stats(EngineStatsRequest(**make_request("summon_thunder_magus", 20)))
    stats = res.get("stats", {})
    assert stats["cast_speed_additional"]["total"] == pytest.approx(0.06)        # +6% (no other cast-add source)
    assert stats["dmg_additional"]["total"] == pytest.approx(0.0725)             # +7.25% additional damage @ L20
    assert stats["attack_speed_additional"]["total"] >= 0.06                     # +6% on top of any dual-wield add


def test_unmodelled_minion_contributes_no_damage_through_engine():
    """The registry gate: with no bespoke module for Summon Fire Magus, the owner comes back as ONE NYI result
    (supported=false, 0 DPS) that still lists its abilities — surfaced, not silently dropped."""
    assert "summon_fire_magus" not in MINION_MODULES  # not modelled
    from tests.mock_build import make_request
    from server import engine_stats, EngineStatsRequest
    res = engine_stats(EngineStatsRequest(**make_request("summon_fire_magus", 20)))
    mo = res.get("minion_offense")
    assert mo and "summon_fire_magus" in mo
    result = mo["summon_fire_magus"]                    # ONE result per owner now
    assert result["supported"] is False and result["total_dps"] == 0.0    # contributes nothing
    assert any("Blazing Dance" in n for n in result["nyi"])   # abilities still listed (surfaced, not dropped)


def test_minion_penetration_reduces_target_mitigation():
    """Minion penetration (minion_<type>_pen_inc / minion_elemental_pen) raises the minion's enemy multiplier
    (less mitigation). It reads the MINION's pen off minion pools — the player's pen never applies to minions."""
    o0 = calculate_minion_offense(BuildSource(), _BASE_SKILL, _BASE_STATS, 20)
    s1 = BuildSource(); s1.add("minion_fire_pen_inc", 0.30)     # +30% fire pen for the minion
    o1 = calculate_minion_offense(s1, _BASE_SKILL, _BASE_STATS, 20)
    assert o1.enemy_mult_by_type["fire"] > o0.enemy_mult_by_type["fire"]
    # The player's own pen must NOT help the minion.
    sp = BuildSource(); sp.add("fire_pen", 0.30)               # PLAYER fire pen
    op = calculate_minion_offense(sp, _BASE_SKILL, _BASE_STATS, 20)
    assert op.enemy_mult_by_type["fire"] == pytest.approx(o0.enemy_mult_by_type["fire"])


def test_thunder_magus_folds_spirit_magi_damage_pools():
    """Spirit-Magi-scoped damage (spirit_magi_dmg_inc, tag `spirit_magi`) would be dropped by the minion offense's
    `minion`-tag filter — the magus module folds it into the generic minion pool so it applies."""
    owner, base_stats = _thunder_owner_and_stats()
    r = MINION_MODULES["summon_thunder_magus"](
        _seeded(BuildSource(), spirit_magi_dmg_inc=0.5), owner, base_stats, 20, 1)
    assert r.generic_inc >= 0.5      # +50% Spirit Magi Skill Damage folded into the minion increased pool


def test_thunder_magus_empower_effect_scales_euphoria():
    """The Euphoria buff scales by the MINION/magi Empower Effect (spirit_magi_empower_effect_additional), not the
    player's: +35% AS × (1 + Empower Effect) × uptime."""
    owner, base_stats = _thunder_owner_and_stats()
    r = MINION_MODULES["summon_thunder_magus"](
        _seeded(BuildSource(), spirit_magi_empower_effect_additional=0.5), owner, base_stats, 20, 1)
    ls = next(f for f in r.hit_forms if "Lightning Star" in f.name)
    cast_slot = 1 - 0.5 * (0.6 / 10)   # Empower cast-slot on the 10 s cooldown
    assert ls.fires_per_sec == pytest.approx((1 / 0.8) * (1 + 0.35 * 1.5 * 0.6) * cast_slot)


def test_isomorphic_arms_transfers_weapon_bonuses_and_conditional_spell_damage():
    """God of Machines 'Isomorphic Arms': the main-hand weapon's Base Damage transfers to the minion (but NOT its
    Base Attack Speed / Crit), and '+30% additional Spell Damage for Minions when wielding a Wand/Tin Staff' applies."""
    from tests.mock_build import make_request
    from server import engine_stats, EngineStatsRequest
    mods = ["Minions gain the Main-Hand Weapon's bonuses",
            "+30% additional Spell Damage for Minions when wielding a Wand or Tin Staff"]
    base = engine_stats(EngineStatsRequest(**make_request("summon_thunder_magus", 20)))
    iso = engine_stats(EngineStatsRequest(**make_request(
        "summon_thunder_magus", 20, custom_mods=mods, extra_conditions={"wielding_wand_or_tin_staff": True})))
    d = lambda r: r["minion_offense"]["summon_thunder_magus"]["total_dps"]
    assert d(iso) > d(base)
    st = iso.get("stats", {})
    assert st.get("minion_physical_dmg_flat_min", {}).get("total", 0) == 200.0    # weapon1 base damage transferred
    assert st.get("minion_spell_dmg_additional", {}).get("total", 0) == pytest.approx(0.3)
    assert "minion_weapon_attack_speed" not in st                                 # base AS NOT transferred


def _seeded(src, **kv):
    for k, v in kv.items():
        src.add(k, v)
    return src


_ATTACK_ABILITY = {"name": "Atk", "skill_tags": ["Base Skill", "Attack", "Fire"],
                   "base_damage_coefficient": 232.0, "cast_speed": "0.8 s"}
_SPELL_ABILITY = {"name": "Spl", "skill_tags": ["Base Skill", "Spell", "Fire"],
                  "base_damage_coefficient": 232.0, "cast_speed": "0.8 s"}


def test_minion_spell_and_attack_pools_never_mix():
    """CRITICAL: a minion's Spell-damage pool must NOT touch an Attack ability, and vice versa."""
    s = BuildSource(); s.add("minion_spell_dmg_additional", 0.5)      # +50% additional Spell Damage for Minions
    attack = calculate_minion_offense(s, _ATTACK_ABILITY, _BASE_STATS, 20)
    spell = calculate_minion_offense(s, _SPELL_ABILITY, _BASE_STATS, 20)
    assert attack.generic_add == pytest.approx(1.0)                   # spell pool excluded from the attack
    assert spell.generic_add == pytest.approx(1.5)                    # applies to the spell
    # A generic (untagged) minion pool applies to both.
    sg = BuildSource(); sg.add("minion_dmg_additional", 0.5)
    assert calculate_minion_offense(sg, _ATTACK_ABILITY, _BASE_STATS, 20).generic_add == pytest.approx(1.5)


def test_minion_skill_level_above_max_multiplier():
    """+Minion Skill Level scales like any skill above max level: ×1.10 per level 21-30, ×1.08 per level 31+."""
    o0 = calculate_minion_offense(BuildSource(), _ATTACK_ABILITY, _BASE_STATS, 20)
    for n, exp in [(2, 1.10 ** 2), (10, 1.10 ** 10), (15, 1.10 ** 10 * 1.08 ** 5)]:
        s = BuildSource(); s.add("minion_skill_level", n)
        o = calculate_minion_offense(s, _ATTACK_ABILITY, _BASE_STATS, 20)
        assert o.effective_level == 20 + n
        assert o.above_max_mult == pytest.approx(exp)
        assert o.total_dps / o0.total_dps == pytest.approx(exp)
    # spirit_magi_skill_level stacks with minion_skill_level.
    s2 = BuildSource(); s2.add("minion_skill_level", 1); s2.add("spirit_magi_skill_level", 1)
    assert calculate_minion_offense(s2, _ATTACK_ABILITY, _BASE_STATS, 20).above_max_mult == pytest.approx(1.10 ** 2)


def test_talons_per_growth_additional_fold():
    from engine.minion_offense import fold_spirit_magi_pools
    s = BuildSource(); s.add("minion_dmg_additional_per_20_growth", 0.01); fold_spirit_magi_pools(s, 300)  # floor(300/20)=15
    assert calculate_minion_offense(s, _ATTACK_ABILITY, _BASE_STATS, 20).generic_add == pytest.approx(1.15)


def test_focused_strike_at_center_area_scoped():
    _area = {"name": "Ar", "skill_tags": ["Base Skill", "Attack", "Fire", "Area"], "base_damage_coefficient": 232.0, "cast_speed": "0.8 s"}
    s = BuildSource(); s.add("minion_at_center_dmg_additional", 0.32)
    assert calculate_minion_offense(s, _area, _BASE_STATS, 20).generic_add == pytest.approx(1.32)          # area
    assert calculate_minion_offense(s, _ATTACK_ABILITY, _BASE_STATS, 20).generic_add == pytest.approx(1.0)  # not area


def test_queer_angle_lucky_raises_average_with_spread():
    # Lucky raises a type's average from the midpoint toward the max (min + 2/3 range) — needs a damage spread.
    def dps(lucky):
        s = BuildSource(); s.add("minion_fire_dmg_flat_min", 0); s.add("minion_fire_dmg_flat_max", 4640)
        if lucky: s.add("minion_lucky_fire", 1.0)
        return calculate_minion_offense(s, _ATTACK_ABILITY, _BASE_STATS, 20).total_dps
    assert dps(True) / dps(False) == pytest.approx(7.0 / 6.0, rel=1e-3)   # midpoint→lucky for a 0..R + base spread


def test_minion_multistrike_mirrors_player_formula():
    """Minion multistrike = the player model: chance auto-repeats the attack with increasing damage, +20%
    multistrike AS diluting against the minion's increased AS. Spell abilities never multistrike."""
    o0 = calculate_minion_offense(BuildSource(), _ATTACK_ABILITY, _BASE_STATS, 20)
    s = BuildSource(); s.add("minion_multistrike_chance", 1.16); s.add("minion_multistrike_increasing_dmg_inc", 0.55)
    o = calculate_minion_offense(s, _ATTACK_ABILITY, _BASE_STATS, 20)
    # c=1.16, inc=0.55, s=1.2 → mult = (0.84·2.55 + 0.16·4.65) / (0.84·(2/1.2) + 0.16·(3/1.2)) = 1.6033
    assert o.multistrike_mult == pytest.approx(1.6033, rel=1e-4)
    assert o.total_dps / o0.total_dps == pytest.approx(o.multistrike_mult)
    assert o.multistrike_max_count == 3 and o.multistrike_avg_count == pytest.approx(2.16)
    # A SPELL minion ability does not multistrike.
    _spell = {"name": "S", "skill_tags": ["Base Skill", "Spell", "Fire"], "base_damage_coefficient": 232.0, "cast_speed": "0.8 s"}
    assert calculate_minion_offense(s, _spell, _BASE_STATS, 20).multistrike_mult == 1.0
