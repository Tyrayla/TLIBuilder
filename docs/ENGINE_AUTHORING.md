# Engine Authoring Reference

Shared reference for adding game mechanics to the DPS engine. The `.claude/skills/add-*` skills link here so the
gotchas and verify steps live in one place. Humans can read this top-to-bottom; skills cite the relevant section.

> **Never reference other game titles** anywhere (code, comments, docs). This is TLI Builder for *Torchlight:
> Infinite* only.

---

## Approval-gate policy (every authoring skill obeys this)

1. **Propose, then wait.** Present the EXACT implementation — the code stub AND the per-tier values/formulas —
   and get the owner's explicit approval before writing anything. Nothing lands that the owner didn't approve.
2. **Surface uncertainties, never guess them in.** Any formula, per-tier number, pooling rule (increased vs
   additional), or interaction you're not certain of is flagged for the owner to confirm — not silently assumed.
3. **Never silently drop.** Every line of a mechanic is either modelled or surfaced (status row / NYI badge).
4. **No commit without asking.** Author + verify; the owner decides when to commit (and separately, to push).

---

## Verify commands (the `/engine-verify` skill automates these)

- **Typecheck** (repo root): `npx tsc --noEmit -p tsconfig.web.json` — count `error TS`. Pre-existing errors in
  in-progress Zustand files are expected; you own only errors in files you touched.
- **Python tests** (`cd backend`): `python -m pytest -q`. For one file: `python -m pytest tests/test_x.py -q`.
- **Consumable-universe scan**: `python -m pytest tests/test_consumable_universe.py -q` (see gotcha below).
- **Golden re-capture** (only when engine output legitimately changed): delete the changed fixtures under
  `backend/tests/fixtures/{support_skill_golden,scope_golden}/*.json`, run the golden tests once (captures +
  skips), then again (asserts). **Before accepting, diff old→new for additive-only** (no pre-existing value
  changed — only new keys added). If a pre-existing value changed, that's a real behavior change to review, not a
  mechanical re-capture.

---

## Gotchas that have broken tests

- **Consumable-universe whitelist.** `tests/test_consumable_universe.py` scans every `backend/engine/*.py` for
  `source.total/get/sum("literal")` and fails if a stat that's in `STAT_META` is read but missing from the
  universe. When you add a stat the engine reads on *every* run (offense `_enemy_vuln_mult`, aggregator, defense),
  add it to the `consumed |= {...}` block in `backend/engine/consumable_universe.py`. (Engine-injected stats with
  NO `StatMeta`, like `paralysis_dmg_taken`, are skipped by the scan and don't need it.)
- **Goldens change when output changes.** Adding fields to `OffenseResult`/`HitFormResult`, or a new always-read
  stat (it enters every skill's `consumed_stats`), changes `support_skill_golden/*` + `scope_golden/*`. These are
  usually *additive* — re-capture with the additive-only diff check above. A NEW registered skill (`_register`)
  also auto-captures a new `support_skill_golden/<id>.json`.
- **`stat_meta` completeness.** `StatMeta` is REQUIRED for any node-modifiable / user-facing stat — every
  `NODE_MODIFIER_POOL` stat must have an entry (enforced by `test_models_stat_meta.py`), and any stat that should
  show a clean display name in the Calcs breakdown needs one. It is OPTIONAL for engine-injected/derived stats that
  are read only by explicit key and never surface (e.g. `paralysis_dmg_taken`, the consume `_unit`/`_cap`/flag
  stats, the per-N-consumed source stats). Access is always graceful (`STAT_META.get(...)`), so a missing entry
  degrades to "no display name + excluded from the meta-driven pipelines", never a crash. `test_models_stat_meta.py`
  does NOT assert every `Stat` has meta — only `NODE_MODIFIER_POOL` coverage + validity of the entries present.

---

## Touchpoint maps

### Add a stat
1. `backend/models/stat.py` — `Stat.<NAME> = "<snake_key>"` (under the right `# ── category ──` block).
2. `backend/models/stat_meta.py` — `StatMeta(display, category, modifier_type, unit, subgroup=, pipeline_stage=,
   tags=, affects=, stacking_rule=, ui_priority=, source_types=)`.
   - `pipeline_stage` decides WHERE it's read (`increased_reduced`, `additional`, `enemy_vulnerability`,
     `crit_rating`, `crit_damage`, `attribute`, `mitigation`, …). Wrong stage ⇒ never consumed.
   - `tags=()` = universal; `tags=("spell","cold")` = only skills with those tags. `affects` = `_HIT` or `_HIT_DOT`.
   - `source_types=()` for engine-injected (no UI source editor); else e.g. `_T`/`_TB`.
3. **If always-read by the engine:** add to `backend/engine/consumable_universe.py` `consumed |= {...}`.

### Add a condition
1. `data/conditions.json` — append a ConditionDef: `key,label,category,value_type("boolean"|"numeric"),
   numeric_min,numeric_max,min_base,min_from_stat,max_base,max_from_stat,unit,default_value,default_bool,
   visible,source`. Hero-trait-gated ⇒ `category:"Hero Trait"` + `trait_id:"<id>"` (UI shows only for that trait).
2. `backend/server.py` `_COND_PATTERNS` — only if generic gear/affix text must translate to this condition:
   boolean phrase → `"key"` (or `{"not":"key"}`); per-scaling → `{"key":"key","op":"per","divisor":N}` (+ `cap`).
   A bespoke module that reads `condition_state` directly does NOT need a pattern.
3. UI: boolean toggles fall back to `default_bool` when unset (Conditionals screen); numeric to `default_value`.

### Add a hero trait (bespoke module)
1. `backend/engine/hero_traits/<id>.py` — `TRAIT_ID="<id>"` (matches `_hero_traits.json`); hooks:
   - `apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks) -> {"contributions":[...], "numbed_stacks": float|None}`
   - `stash(*, source, ls_state, inflict_aps) -> None` (capture converged scalars for next pass; loop converges ~3 passes)
   - `status_lines(*, slot_levels, advanced_picks) -> list[{text,source,status}]` (one per line — never silently drop)
   - Helpers: `_contrib(stat_key,amount,text,source)`, `_tier(slot_levels,idx)` (uses `abs`), `_enabled(slot_levels,idx)`
     (a DISABLED node is a NEGATIVE slot level — gate every tier on `_enabled`), `_flag(condition_state,key,default)`.
2. Register: `backend/engine/hero_traits/__init__.py` — import + add to `_MODULES`. (`server.py` routes via `has_module`.)
3. Data: map EVERY line of the trait from `data/seasons/SS12/_hero_traits.json` verbatim; spatial/regen lines →
   `status_lines` as `informational`.
4. New pools/inputs ⇒ run `/add-stat` and `/add-condition`.
5. Test: `backend/tests/test_<id>.py` (mirror `test_high_court_chariot.py`; `mock_build.make_request(skill, lvl,
   trait_id=, trait_slot_levels=, advanced_trait_selections=, extra_conditions=)`). Measure trait DELTAs vs
   `trait_id=None` (the mock build has baselines like dual-wield block chance).

### Add a skill resolver (spell / attack / channeled)
1. `backend/engine/skill_resolver.py` — `@_register("<id>")` → `ResolvedSkill`:
   - Spell: `is_spell=True`, `base_dmg_by_level={lvl:{dtype:(min,max)}}`, `base_cast_time`,
     `added_dmg_effectiveness`, `damage_types`. **Spell base is NOT scaled by effectiveness** — only ADDED flat is
     (forms keep `effectiveness_pct=100`). Multi-form spells set `base_dmg`/`added_eff` PER `SkillHitForm`.
   - Attack: `hit_forms_by_level={lvl:[SkillHitForm(...)]}` parsed from progression; weapon supplies base.
   - Channeled: add `channeled=ChanneledSpec(max_stacks,min_stacks,behavior("reset"|"refresh"),
     burst_replaces_continuous, continuous_suppression_when_bursting)`; per-form `channel_role`
     ("continuous"=every use | "burst"=once per cycle), `hit_count`, `shotgun_falloff`, `scales_with_projectiles`.
     Cadence: `engine/uptime.channeled_rounds_per_cycle = max(1, Max−Min)`. **All channeled skills cast at 3/s.**
2. Data: `data/seasons/SS12/_skills.json` (item_id, name, skill_tags, progression, cast_speed, max_level). A
   trait-granted/synthetic skill can be injected into `skills_by_id` server-side (see `rosa_holy_domain` in `server.py`).
3. Test (mirror `test_channeled.py`/`test_group1_offense.py`) + golden (new `_register` auto-captures
   `support_skill_golden/<id>.json` — run twice).

### Add a support gem
1. **Generic first.** `backend/engine/support_resolver.py` parses progression lines into `dmg_additional`-style
   contributions for most supports — NO code needed. Only go bespoke if the generic path mis-parses or the support
   has a conditional/special mechanic.
2. Bespoke: `backend/engine/skill_effects/<id>.py` — `SKILL_ID`, optional `GUARD_IDS` (skip the generic line),
   `CONTRIB_HOOKS` (type-A support-path contribution), `apply_slot_effects` (type-B slot-local emits),
   `preseed` (type-C condition seeding — must fire per-slot). Register in `skill_effects/__init__.py` `_MODULES`.
   Additional pools multiply per distinct source; form-scoped lines gate on the form's `proc_stat_key`.

---

## Reference implementations to copy
- Hero trait: `backend/engine/hero_traits/high_court_chariot.py`, `lightning_shadow.py` (+ `README.md`).
- Skill resolver: `chain_lightning` (spell), `icebound_beam` (channeled multi-form), the slash skills (attack) in
  `backend/engine/skill_resolver.py`.
- Channeled framework: `ChanneledSpec` + `engine/uptime.py` + `engine/offense.py` per-form rate; `test_channeled.py`.
- Support (bespoke): `backend/engine/skill_effects/berserking_blade.py` (+ `README.md`).
- Test harness: `backend/tests/mock_build.py` (`make_request`, `character_contributions`, `weapon`, `DUAL_WEAPONS`).
