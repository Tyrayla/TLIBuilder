# Resolver snippets to ADD to backend/engine/skill_resolver.py (pick the variant; fill placeholders).
# Reference live examples: chain_lightning (spell), icebound_beam (channeled multi-form), the slash skills (attack).

# ── SPELL ────────────────────────────────────────────────────────────────────────
# Spell base damage scales per LEVEL and is NOT scaled by effectiveness — only ADDED flat is. Forms keep
# effectiveness_pct=100; the real added-damage effectiveness rides added_dmg_effectiveness (or per-form added_eff).
@_register("<skill_id>")
def _resolve_<skill_id>(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {e["level"]: e["values"] for e in skill_data.get("progression", [])}
    base_by_level: dict[int, dict[str, tuple[float, float]]] = {}
    effectiveness = 1.0
    damage_types: list[str] = []
    for lvl, values in progression.items():
        text = " ".join(str(v) for v in values.values())
        m = _SPELL_BASE_DMG_RE.search(text)          # "Deals X-Y Spell <Type> Damage"
        if m:
            base_by_level[lvl] = {m.group(3).lower(): (float(m.group(1).replace(",", "")),
                                                        float(m.group(2).replace(",", "")))}
            if m.group(3).lower() not in damage_types:
                damage_types.append(m.group(3).lower())
        eff = values.get("Effectiveness of added damage")
        if eff:
            em = re.search(r"(\d+(?:\.\d+)?)", str(eff))
            if em:
                effectiveness = float(em.group(1)) / 100.0
    forms_by_level = {lvl: [SkillHitForm("<Skill Name>", 100.0, "additive")] for lvl in base_by_level}
    return ResolvedSkill(
        skill_id=skill_data["item_id"], name=skill_data["name"], tags=skill_data.get("skill_tags", []),
        max_level=max_level, hit_forms_by_level=forms_by_level, supported=True, is_spell=True,
        base_dmg_by_level=base_by_level, base_cast_time=_parse_cast_time(skill_data.get("cast_speed", "")),
        added_dmg_effectiveness=effectiveness, damage_types=damage_types,
    )

# ── ATTACK ───────────────────────────────────────────────────────────────────────
# Weapon supplies base damage; parse the hit form(s) (% Weapon Attack Damage) from the progression Descript.
@_register("<skill_id>")
def _resolve_<skill_id>(skill_data: dict) -> ResolvedSkill:
    max_level = skill_data.get("max_level", 20)
    progression = {e["level"]: e["values"] for e in skill_data.get("progression", [])}
    forms_by_level: dict[int, list[SkillHitForm]] = {}
    for lvl, values in progression.items():
        # m = re.search(r"(\d+(?:\.\d+)?)%\s*Weapon Attack Damage", values.get("Descript", ""))
        forms_by_level[lvl] = [SkillHitForm("<Skill Name>", <eff_pct>, "additive")]
    return ResolvedSkill(
        skill_id=skill_data["item_id"], name=skill_data["name"], tags=skill_data.get("skill_tags", []),
        max_level=max_level, hit_forms_by_level=forms_by_level, supported=True,
    )

# ── CHANNELED (spell or attack) ──────────────────────────────────────────────────
# Add a ChanneledSpec + per-form channel_role. continuous = every use; burst = once per RESET cycle
# (rounds = max(1, Max-Min) via uptime.channeled_rounds_per_cycle). ALL channeled skills cast at 3/s.
# Multi-form spell: each form carries its own base_dmg + added_eff. Burst form may shotgun (hit_count/falloff)
# and scale with projectile quantity (scales_with_projectiles=True).
        channeled=ChanneledSpec(max_stacks=<N>, min_stacks=0, behavior="reset",   # or "refresh"
                                burst_replaces_continuous=False,
                                continuous_suppression_when_bursting=1.0),         # <1.0 = beam-style redistribution
        hit_forms_by_level={lvl: [
            SkillHitForm("<Continuous>", 100.0, "additive", base_dmg={"<type>": <base>}, added_eff=<eff>,
                         channel_role="continuous"),
            SkillHitForm("<Burst>", 100.0, "additive", base_dmg={"<type>": <base>}, added_eff=<eff>,
                         channel_role="burst", hit_count=<n>, shotgun_falloff=<f>, scales_with_projectiles=<bool>),
        ]},
