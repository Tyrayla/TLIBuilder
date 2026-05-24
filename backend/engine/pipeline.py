from __future__ import annotations
from engine.models import BuildSource, SkillConfig, EnemyConfig, ComputedResult

_ELEMENTAL_TYPES = frozenset({"fire", "cold", "lightning", "erosion"})

# Armor mitigation constant. Tune this to match in-game values.
# Formula: reduction = armor / (armor + ARMOR_K)
ARMOR_K = 1000.0


def run_pipeline(
    source: BuildSource,
    skill: SkillConfig,
    enemy: EnemyConfig,
) -> ComputedResult:
    tags        = set(skill.tags)
    dmg_types   = set(skill.damage_types)
    is_elemental = bool(dmg_types & _ELEMENTAL_TYPES)

    # ── Stage 1: Base + Flat ───────────────────────────────────────────────────
    flat_min = skill.base_dmg_min
    flat_max = skill.base_dmg_max

    for dt in dmg_types:
        if "attack" in tags:
            flat_min += source.total(f"{dt}_attack_dmg_flat_min")
            flat_max += source.total(f"{dt}_attack_dmg_flat_max")
        if "spell" in tags:
            flat_min += source.total(f"{dt}_spell_dmg_flat_min")
            flat_max += source.total(f"{dt}_spell_dmg_flat_max")

    avg_base = (flat_min + flat_max) / 2.0

    # ── Stage 2: Increased/Reduced (one additive pool) ─────────────────────────
    inc = source.total("dmg_inc")
    if "attack"      in tags:     inc += source.total("attack_dmg_inc")
    if "spell"       in tags:     inc += source.total("spell_dmg_inc")
    if "melee"       in tags:     inc += source.total("melee_dmg_inc")
    if "area"        in tags:     inc += source.total("area_dmg_inc")
    if "projectile"  in tags:     inc += source.total("projectile_dmg_inc")
    if "minion"      in tags:     inc += source.total("minion_dmg_inc")
    if "sentry"      in tags:     inc += source.total("sentry_dmg_inc") if False else 0  # no stat yet
    if is_elemental:               inc += source.total("elemental_dmg_inc")
    for dt in dmg_types:           inc += source.total(f"{dt}_dmg_inc")

    inc_factor = 1.0 + inc

    # ── Stage 3: Additional (each qualifying bucket × independently) ───────────
    # Same stat value pools additively within its bucket; different stat keys multiply.
    additional_buckets: list[tuple[str, bool]] = [
        ("dmg_additional",                True),
        ("attack_dmg_additional",         "attack"      in tags),
        ("spell_dmg_additional",          "spell"       in tags),
        ("melee_dmg_additional",          "melee"       in tags),
        ("area_dmg_additional",           "area"        in tags),
        ("projectile_dmg_additional",     "projectile"  in tags),
        ("minion_dmg_additional",         "minion"      in tags),
        ("sentry_dmg_additional",         "sentry"      in tags),
        ("elemental_dmg_additional",      is_elemental),
        ("enemy_nearby_dmg_taken_additional", True),
    ]
    for dt in dmg_types:
        additional_buckets.append((f"{dt}_dmg_additional", True))

    additional_factors: list[float] = []
    for stat_key, applies in additional_buckets:
        if applies:
            val = source.total(stat_key)
            if val != 0.0:
                additional_factors.append(1.0 + val)

    # ── Stage 4: Attribute factor ──────────────────────────────────────────────
    # STR → physical/attack, DEX → attack/projectile, INT → spell/elemental.
    # Sum all relevant attribute points; 0.5% additional damage per point.
    relevant_attrs = 0.0
    if "attack" in tags or "physical" in dmg_types:
        relevant_attrs += source.total("strength")
    if "attack" in tags or "projectile" in tags:
        relevant_attrs += source.total("dexterity")
    if "spell" in tags or is_elemental:
        relevant_attrs += source.total("intelligence")

    attr_factor = 1.0 + relevant_attrs * 0.005

    # ── Stage 5: Skill level → skill multiplier ────────────────────────────────
    extra = skill.extra_levels
    extra += int(source.total("all_skill_level"))
    extra += int(source.total("active_skill_level"))
    extra += int(source.total(f"{skill.skill_type}_skill_level"))
    for tag in skill.tags:
        if tag not in ("attack", "spell"):
            extra += int(source.total(f"{tag}_skill_level"))
    for dt in dmg_types:
        extra += int(source.total(f"{dt}_skill_level"))

    effective_level   = skill.base_level + extra
    levels_above_30   = max(0, effective_level - 30)
    skill_multiplier  = 1.08 ** levels_above_30

    # ── Stage 6: Critical strike ───────────────────────────────────────────────
    # CSR: base + flat bonuses, then × (1 + Σ inc%)
    base_csr = skill.base_csr
    base_csr += source.total(f"{skill.skill_type}_crit_rating_flat")
    if "minion" in tags:
        base_csr += source.total("minion_crit_rating_flat")

    csr_inc = source.total(f"{skill.skill_type}_crit_rating_inc")
    if "minion" in tags:
        csr_inc += source.total("minion_crit_rating_inc")

    csr_final   = base_csr * (1.0 + csr_inc)
    crit_chance = min(csr_final / 100.0, 1.0)

    crit_dmg = 1.50  # default
    crit_dmg += source.total("crit_dmg_inc")
    crit_dmg += source.total(f"{skill.skill_type}_crit_dmg_inc")
    if "minion" in tags:
        crit_dmg += source.total("minion_crit_dmg_inc")
    for dt in dmg_types:
        crit_dmg += source.total(f"{dt}_crit_dmg_inc")

    crit_factor = 1.0 + crit_chance * (crit_dmg - 1.0)

    # ── Stage 7: Double damage (Hit only, expected value) ──────────────────────
    dd_chance = source.total("double_dmg_chance")
    if "attack" in tags:  dd_chance += source.total("attack_double_dmg_chance")
    if "spell"  in tags:  dd_chance += source.total("spell_double_dmg_chance")
    if "minion" in tags:  dd_chance += source.total("minion_double_dmg_chance")
    if "synth"  in tags:  dd_chance += source.total("synth_double_dmg_chance")
    dd_chance     = min(max(dd_chance, 0.0), 1.0)
    double_factor = 1.0 + dd_chance

    # ── Stage 8: Mitigation ────────────────────────────────────────────────────
    # Physical: armor mitigation only (no resistance).
    # Elemental: resistance mitigation only (armor doesn't apply).
    # Penetration reduces the effective resistance/armor used in calculation only.
    mitigation_factor = 1.0
    for dt in dmg_types:
        if dt == "physical":
            armor_pen = source.total("armor_pen")
            eff_armor = enemy.armor * (1.0 - armor_pen)
            eff_armor = max(0.0, eff_armor)
            reduction = eff_armor / (eff_armor + ARMOR_K)
            mitigation_factor *= (1.0 - reduction)
        elif dt in _ELEMENTAL_TYPES:
            pen = source.total(f"{dt}_pen") + source.total("elemental_pen")
            enemy_res = getattr(enemy, f"{dt}_resistance", 0.0)
            # all_resistance_reduction is stored as a negative value (e.g. -0.08 for -8%)
            eff_res   = enemy_res - pen + source.total("all_resistance_reduction")
            mitigation_factor *= (1.0 - eff_res)

    # ── Combine ────────────────────────────────────────────────────────────────
    result_min = flat_min
    result_max = flat_max
    for factor in [inc_factor, *additional_factors, attr_factor, skill_multiplier,
                   crit_factor, double_factor, mitigation_factor]:
        result_min *= factor
        result_max *= factor

    avg_hit = (result_min + result_max) / 2.0

    return ComputedResult(
        avg_hit         = round(avg_hit, 2),
        min_hit         = round(result_min, 2),
        max_hit         = round(result_max, 2),
        crit_chance     = round(crit_chance, 4),
        crit_multiplier = round(crit_dmg, 4),
        effective_dps   = round(avg_hit, 2),  # placeholder; needs attack speed
        breakdown       = {
            "avg_base":         round(avg_base, 4),
            "inc_factor":       round(inc_factor, 4),
            "additional":       [round(f, 4) for f in additional_factors],
            "attr_factor":      round(attr_factor, 4),
            "skill_multiplier": round(skill_multiplier, 4),
            "crit_chance":      round(crit_chance, 4),
            "crit_multiplier":  round(crit_dmg, 4),
            "crit_factor":      round(crit_factor, 4),
            "double_factor":    round(double_factor, 4),
            "mitigation_factor":round(mitigation_factor, 4),
            "effective_level":  effective_level,
        },
    )
