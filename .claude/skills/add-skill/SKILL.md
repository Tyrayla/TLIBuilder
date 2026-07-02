---
name: add-skill
description: Add an active skill (spell, attack, or channeled) to the TLI Builder DPS engine — a skill_resolver entry returning a ResolvedSkill, plus a test and golden. Use when modeling a new damage skill, e.g. a channeled beam like Howling Gale, a new spell, or an attack skill. Scaffold + checklist; approval-gated.
---

# add-skill

Scaffolds a skill resolver + the wiring checklist. **Approval-gated** — propose the exact resolver + parsed values
and wait for Tyra's OK. Read `docs/ENGINE_AUTHORING.md` (Add a skill resolver) first. Live references:
`chain_lightning` (spell), `icebound_beam` (channeled multi-form), the slash skills (attack) in
`backend/engine/skill_resolver.py`; channeled validated in `test_channeled.py` + `[[project_channeled_framework]]`.

## 1. Gather the skill data
- Find the skill in `data/seasons/SS12/_skills.json` (by `item_id`). Note `skill_tags`, `cast_speed`, `max_level`,
  `effectiveness_of_added_damage`, and the per-level `progression` (base damage, hit-form %s, descriptions).
- Classify: **spell** (intrinsic per-level base + cast time) vs **attack** (weapon-driven, % Weapon Attack Damage)
  vs **channeled** (held; stacks; reset/refresh). Multi-form? (e.g. a continuous hit + a burst).
- Flag uncertainties for Tyra: effectiveness mapping (per-form?), shotgun/projectile behavior, max channeled
  stacks if the line omits it, reset-vs-refresh, any redistribution (continuous suppression). **Surface, don't guess.**

## 2. Propose (do not write yet)
Fill the matching variant from `templates/resolver.py` (in this skill folder) with the parsed values, and
`templates/test.py`. Key rules it encodes:
- **Spell base is NOT scaled by effectiveness** — only ADDED flat is (forms keep `effectiveness_pct=100`,
  effectiveness rides `added_dmg_effectiveness` / per-form `added_eff`). Multi-form spell ⇒ per-form `base_dmg`.
- **Channeled:** `ChanneledSpec(max_stacks,min_stacks,behavior,burst_replaces_continuous,
  continuous_suppression_when_bursting)` + per-form `channel_role` ("continuous"/"burst"), `hit_count`,
  `shotgun_falloff`, `scales_with_projectiles`. Cadence `max(1,Max−Min)`; cast rate 3/s.
Show Tyra the filled resolver + the parsed per-level numbers for sign-off.

## 3. Apply (after approval)
- [ ] `backend/engine/skill_resolver.py` — add the `@_register("<id>")` resolver. Reuse module helpers
      (`_parse_cast_time`, `_SPELL_BASE_DMG_RE`, `_parse_pct`); add a regex constant if the parse is bespoke.
- [ ] Data: ensure the skill exists in `data/seasons/SS12/_skills.json`. A trait-granted/synthetic skill is
      injected into `skills_by_id` server-side instead (pattern: `rosa_holy_domain` in `server.py`).
- [ ] `backend/tests/test_<id>.py` from the template — assert supported, base-damage (unscaled), and (channeled)
      the per-form cadence / Min behavior.

## 4. Verify
Run `/engine-verify`. A newly `@_register`'d skill auto-captures `tests/fixtures/support_skill_golden/<id>.json`
(run the golden test twice). Do not commit. Offer RECOUNT validation for channeled skills.

## 5. Verification entry (anti-drift)
Run `/add-verification` so the new skill gets a Verification Database entry (status `unverified` unless you
have RECOUNT data). A newly registered skill lacking an entry is flagged by engine-verify's drift check.
