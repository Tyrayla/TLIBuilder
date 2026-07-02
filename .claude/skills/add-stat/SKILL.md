---
name: add-stat
description: Add a new stat to the TLI Builder DPS engine — the Stat enum entry, its StatMeta, and the consumable-universe whitelist if it's always-read. Use when adding a new modifier/stat pool (damage/defense/attribute/enemy-vulnerability), or when a hero trait / skill / support needs a stat that doesn't exist yet. Scaffold + checklist; approval-gated.
---

# add-stat

Scaffolds a new engine stat and gives the exact edit checklist. **Approval-gated** — propose the exact stat +
`StatMeta` and wait for the owner's OK before writing. See `docs/ENGINE_AUTHORING.md` (Add a stat, gotchas).

## 1. Gather
Ask / confirm with the owner:
- **What the stat represents** and its in-game wording (so the display name + `modifier_type` match).
- **key** (snake_case) + enum name (SCREAMING_SNAKE).
- **pipeline_stage** — where the engine reads it: `increased_reduced` | `additional` | `enemy_vulnerability` |
  `crit_rating` | `crit_damage` | `attribute` | `mitigation` | … (wrong stage ⇒ never consumed).
- **tags** — `()` universal, or the skill tags it filters to (e.g. `("spell","cold")`). **affects** — `_HIT` or `_HIT_DOT`.
- **source_types** — `()` if engine-injected (no UI editor), else the editable source set (e.g. `_T`, `_TB`).
- **Is it read on every engine run?** (a `source.total("key")` in offense/aggregator/defense) → needs the universe.

## 2. Propose (do not write yet)
Show the owner the exact additions and the consumed-universe decision:
```python
# backend/models/stat.py  (under the right "# ── category ──" block)
<ENUM_NAME> = "<snake_key>"

# backend/models/stat_meta.py
Stat.<ENUM_NAME>: StatMeta(
    "<Display Name>", "<Category>", "<modifier_type>", "<unit '' or %>",
    subgroup="<subgroup>", pipeline_stage="<stage>",
    tags=(<tags>), affects=<_HIT|_HIT_DOT>,
    stacking_rule="additive", ui_priority=<n>, source_types=<srcs>,
)
```
Copy a sibling stat in the same category as the template (e.g. mirror `NUMBED_LIGHTNING_TAKEN` for an
enemy-vulnerability pool, a `*_dmg_inc` for an increased pool). **Flag any field you're unsure of.**

## 3. Apply (after approval)
- [ ] `backend/models/stat.py` — add the enum member.
- [ ] `backend/models/stat_meta.py` — add the `StatMeta`.
- [ ] **If always-read:** `backend/engine/consumable_universe.py` — add the key to a `consumed |= {...}` block
      with a one-line comment. (Engine-injected stats with NO `StatMeta`, like `paralysis_dmg_taken`, skip this.)
- [ ] Wire the actual read where the stat is consumed (offense/aggregator/defense) — usually part of the
      caller skill (hero trait / support), not this one.

## 4. Verify
Run `/engine-verify` (at minimum `test_models_stat*.py` + the consumable-universe scan). Do not commit.

## 5. Verification entry (anti-drift)
If this stat is part of a mechanic that just shipped, run `/add-verification` so the mechanic gets a
Verification Database entry (status `unverified` unless already tested). Keeps the engine and the KB in sync.
