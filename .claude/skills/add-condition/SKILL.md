---
name: add-condition
description: Add a new user condition/toggle to the TLI Builder engine — a conditions.json entry (boolean or numeric), plus a server _COND_PATTERNS translation if generic gear/affix text must map to it. Use when a mechanic needs a new scenario input (a toggle, a 0-100 resource, a "per X" scaling), including hero-trait-gated conditions. Scaffold + checklist; approval-gated.
---

# add-condition

Scaffolds a new condition and gives the exact edit checklist. **Approval-gated** — propose the exact ConditionDef
(and pattern, if any) and wait for the owner's OK. See `docs/ENGINE_AUTHORING.md` (Add a condition).

## 1. Gather
- **key** + **label** + **category** ("Hero Trait" for trait-gated, else the relevant group).
- **value_type**: `boolean` (toggle) or `numeric` (slider/field).
- Numeric: `numeric_min/max`, `min_base`/`max_base`, optional `min_from_stat`/`max_from_stat` (bound from a stat),
  `unit`, `default_value`. Boolean: `default_bool` (the UI toggle falls back to this when unset).
- **Trait-gated?** → `category:"Hero Trait"` + `trait_id:"<id>"` (UI shows it only when that trait is selected).
- **Does generic gear/affix TEXT need to set it?** If yes, a `_COND_PATTERNS` entry translates the phrase. If a
  bespoke module reads `condition_state["key"]` directly, you do NOT need a pattern.

## 2. Propose (do not write yet)
```json
// data/conditions.json  (append to "conditions")
{
  "key": "<key>", "label": "<Label>", "category": "<Category>",
  "trait_id": "<id or omit>",
  "value_type": "boolean|numeric",
  "numeric_min": 0.0, "numeric_max": null, "min_base": 0.0, "min_from_stat": null,
  "max_base": 0.0, "max_from_stat": null, "unit": "",
  "default_value": 0.0, "default_bool": false, "visible": true, "source": "user"
}
```
If a phrase translation is needed, also propose the `_COND_PATTERNS` entry in `backend/server.py`:
```python
# boolean:  (re.compile(r"...", re.I), "<key>")            # or {"not": "<key>"}
# per-scale:(re.compile(r"per\s+(\d+)\s+...", re.I), lambda m: {"key":"<key>","op":"per","divisor":int(m.group(1))})
```
Mirror an existing hero-trait condition (e.g. `inside_holy_domain`, `murderous_intent`) for the shape. **Flag any
default value or bound you're unsure of.**

## 3. Apply (after approval)
- [ ] `data/conditions.json` — append the ConditionDef. Validate JSON parses:
      `python -c "import json; json.load(open('data/conditions.json',encoding='utf-8'))"`.
- [ ] `backend/server.py` `_COND_PATTERNS` — add the pattern **only if** generic text must map to it.
- [ ] Note: a new always-read condition can change `condition_maximums`/`consumed_stats` goldens → re-capture
      via `/engine-verify`.

## 4. Verify
Run `/engine-verify`. Confirm the condition appears in the Conditionals screen under the right category (and only
for the selected trait, if gated). Do not commit.
