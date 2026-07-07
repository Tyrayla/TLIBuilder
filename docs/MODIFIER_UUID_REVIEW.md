# Modifier Identity (UUID v5) — builder-side review findings

Status: **SHIPPED 2026-07-07 — see the addendum at the bottom.** The review below is preserved
as-written (it drove the final design); the scraper handoff that answered it is
`tlidb-scraper/docs/BUILDER_HANDOFF_IDENTITY.md`.

Original status: review notes, nothing implemented. This is the tlibuilder-side response to the external
scraper's "Modifier Identity (UUID v5)" design spec (localization via stable modifier UUIDs replacing
fragile English text-matching). The spec is directionally correct — UUIDs are the right fix for the
localization problem — but several load-bearing premises are inaccurate against the live engine.
Corrections below, each grounded in code so the next session (either repo) starts from the corrected
model instead of the spec's original claims.

Cross-refs: `docs/ADDITIONAL_DAMAGE_POOLING.md` (the pooling model this review corrects the framing of).

---

## 1. There is no "source" axis — add-vs-multiply keys on normalized *wording*

The spec's central claim — *"the engine decides add-vs-multiply by source: same source → add, different
source → multiply"* — does **not** describe this engine.

`backend/engine/offense.py:198-239` (`_build_additional_factors`) groups contributions by:

```
(stat_key, affix_identity(text))
```

`affix_identity` (`backend/engine/affix_identity.py`) = modifier wording with roll values stripped,
lowercased, punctuation collapsed. `source_type` / `source_name` / `label` exist on `SourceEntry`
(`models.py`) but **never touch the add/multiply math** — they are breakdown-UI attribution only.

Falsifying facts (both are real unit tests in `backend/tests/test_engine_offense.py`):
- **Different items, identical wording → ADD** (`test_identical_affix_across_items_adds`, Gravel +
  Sun-shooter Long Bow → `1.45`).
- **Same item, different wording → MULTIPLY** (`test_distinct_affixes_same_key_multiply` → `1.08×1.08 =
  1.1664`).

Supports *look* source-driven only because `backend/engine/aggregator.py:431-433` mints a **unique text
per support instance** (support id + role) so the wording-key makes each multiply. Implemented through
the text key, not a source branch.

**Correct invariant** (replaces the spec's "preserve the source distinction"):
> The UUID partition of contributions must be byte-identical to `affix_identity`'s partition today —
> same UUID **iff** `affix_identity(a) == affix_identity(b)`. Testable against `TestAdditionalPooling`.

## 2. The proposed canonical template is too coarse → silent DPS regression

The spec templates "off stat + operation family, not the sentence" (`phys_damage · added · flat`).
`affix_identity` deliberately **keeps** wording distinctions that change the math — `One-Handed` vs
`Two-Handed`, plain vs `for the supported skill`, conditional vs unconditional — because those
**multiply**. Collapsing them to one UUID makes them wrongly **ADD**.

The real tension: language-independence wants coarse/structural; pooling fidelity wants fine.
Resolution — mint over a **structured, language-independent descriptor** carrying every identity-bearing
field: `stat_key + pool(increased/additional) + scope(weapon type, skill scope, "for supported skill") +
condition`, roll values excluded. Coarser → pooling regresses; built from the English sentence →
localization regresses. Must be both structured *and* complete.

## 3. `modifier_id` is no longer "unusable" — invert the priority

The spec (inherited from `ADDITIONAL_DAMAGE_POOLING.md` §3) says modifier_id is "null 11,148×". **Stale.**
Current SS12: **2,784 / 3,181 legendary explicit affixes (~87%) carry a non-null `modifier_id`**
(`backend/tools/legendary_gear_importer.py:54-57`). So source-id is the **primary** path for gear
explicits now. BUT **implicits are always null** and **talent-tree effects have no id at all** (raw text
strings, `backend/tools/season_importer.py`) — so the minted template is **mandatory** for the id-less
majority of surfaces. Hybrid is right; just flip the emphasis.

## 4. A second matcher the spec omits: conditions

A modifier's meaning is `(stat_key, pool, condition/scope)`. Stat-key resolution is centralized in one
file (`backend/engine/mod_parser.py` — good). But the **condition** half is a separate English-regex
table: `server.py` `_COND_PATTERNS` / `_translate_condition_expr` ("while on Low Life", "dealt X
recently", "for each Y"), plus the importer's `_COND_RE`. Localization breaks this equally; a
UUID→stat_key lookup drops conditions entirely. The descriptor must encode the condition, or conditions
need their own identity layer.

## 5. Two mechanics the UUID layer must special-case

- **`*_enhancement_additional`** (Tangle/Combo/Focus "Damage Enhancement") pool by **stat-key alone**,
  identity forced to `""` (`offense.py:220`) — they sum regardless of wording. A wording-level UUID used
  as the pooling key would stop them summing. The UUID layer must know which stats pool by key vs identity.
- **Support instances multiply** because the engine mints per-instance-unique text. A pure
  *definition*-level UUID (spec §3: "does not identify the instance") collapses all copies → they'd
  wrongly ADD. Removing text means re-introducing an explicit instance discriminator.

## 6. The goldens do not cover the at-risk path (spec Part 4 parity harness)

There are **10** engine-running goldens, not ~13 (`backend/tests/test_support_skill_goldens.py`,
registry-driven — grows/shrinks with `skill_resolver._REGISTRY`). **None exercise the multi-source
additional-multiply path** — their supports are added-flat / conditional. That path lives only in
`TestAdditionalPooling` / `TestSpeedAdditionalPooling` unit tests. Some goldens also lock present state
for attack skills that currently deal zero damage.

**The parity harness must replay `TestAdditionalPooling` + real gear/talent builds stacking
same-stat/different-wording additionals**, not just the skill goldens, or the regression in §2 ships
uncaught.

## 7. Importer fit (spec Open Q4)

Freeze-after-mint fits, but cannot live on gear records: gear import is **destructive full-replace**,
zero carry-over (`server.py:1649-1660`; `save_legendary_gear` overwrites the whole file). Use a
**separate side-table** keyed on the only stable join today: `item_id` + `affix_identity(text)`.
Precedent: skills carry dev-curated fields across reimport via `_PRESERVE_FIELDS`
(`backend/tools/rebuild_skills.py`) — model the mint store on that.

## Bottom line

Not a "swap the doormat" change. The spec models one surface (stat-key text match); there are **four**:
1. pooling partition at `affix_identity` granularity,
2. condition/scope matcher (`_COND_PATTERNS`),
3. id-less implicits + the full talent tree,
4. support instance identity.

The framing "identity is orthogonal to semantics" is **false in this codebase**: the pooling key *is* the
wording, so template granularity is a semantic decision and must be co-designed with the
additional-pooling rule.

## No-regression gate — BUILT (2026-07-06)

The parity gate from §6 exists: `backend/tests/test_pooling_partition.py` + fixture
`backend/tests/fixtures/pooling_partition/additional_damage_SS12.json` (173 identities / 297 affixes).
It freezes the current `affix_identity` partition over offensive additional-damage affixes (gear
`raw_text` + talent recipe `text`; `#`-templates skipped, "taken" excluded). When the pooling key is
swapped to a minted ID, prove behavior-identical with the provided primitive — no DPS run needed:

```python
induced_partition(new_key_fn, CORPUS) == induced_partition(affix_identity, CORPUS)
```

Compares GROUPINGS, not labels, so a new UUID scheme with different labels passes as long as the same
affixes group together. Two data-independent intent anchors are included (tier/format variants share
identity → ADD; scope variants stay distinct → MULTIPLY). Follow-up extensions: speed-additional and
memory/spirit effect lines. Decision recorded: mint our own IDs, tlidb ids as fallback (not seed, not
identity).

## Key file references

| Concern | Location |
|---|---|
| Additional add/multiply pooling | `backend/engine/offense.py:198-239` (`_build_additional_factors`) |
| Pooling identity function | `backend/engine/affix_identity.py` (+ TS mirror `src/renderer/src/utils/affixIdentity.ts`) |
| Per-instance support text mint | `backend/engine/aggregator.py:431-433` |
| Stat-key text resolution (choke point) | `backend/engine/mod_parser.py` |
| Condition text matcher | `server.py` `_COND_PATTERNS` / `_translate_condition_expr`; importer `_COND_RE` |
| Pooling tests (the real coverage) | `backend/tests/test_engine_offense.py` `TestAdditionalPooling` / `TestSpeedAdditionalPooling` |
| Engine goldens (10, registry-driven) | `backend/tests/test_support_skill_goldens.py` |
| Gear import (full-replace) | `server.py:1649-1660`; `backend/tools/legendary_gear_importer.py` |
| Reimport field carry-over precedent | `backend/tools/rebuild_skills.py` (`_PRESERVE_FIELDS`) |
| Pooling model (framing this corrects) | `docs/ADDITIONAL_DAMAGE_POOLING.md` |

---

## SHIPPED — 2026-07-07 (modifier-identity migration, 5 commits on dev)

The scraper resolved every concern above the right way: it mints
`pooling_uuid = uuid5(4d8c3c25-940d-453e-be66-21a9d603aa0e, canonical_template(text))` where
`canonical_template` is a byte-for-byte copy of `engine/affix_identity.py` — so the §2 tension
dissolved (the template IS our identity; partition preserved by construction), and §1's invariant is
enforced mechanically. What landed builder-side:

1. **Gate first** (`tests/test_scraper_parity_gate.py`): template-join against the scraper's parity
   export; partition + clause-layer equality; strict (zero misses) since the reimport.
2. **Legacy retirement**: the PDF-snapshot path (`talent_snapshot.json`, `talent_parser`,
   `snapshot_diff`, `snapshot_manager`, 6 endpoints) and the single-save path are DELETED;
   `node_type_filter` rebuilds from crawler season trees (the §5 wording drift died with it — the
   "(Max Divinity Effect: N)" suffix now stays in stored text, identity-bearing, with a structured
   `max_divinity_effect: N` parsed at tree import).
3. **Storage**: every imported catalog line stores slim `{text, uuid, pooling_uuid, modifier_id}`
   (`engine/modifier_lines.py`; `slim_checked` degrades ids to null on any wording-changing
   transform). Runtime consumers still see plain strings — unwrapped ONCE at the `season_manager`
   load boundary (`raw=True` for import-merge/identity tooling; never save a normalized view back).
   The §7 side-table became unnecessary: identity lives IN the records; reimports redeliver it
   (`tools/reimport_season.py`, in-process, all entity types).
4. **The key switch**: `engine/identity_index.py` (identity → uuid over stored season files,
   mtime-fingerprint cached) attaches to the BuildSource; all five pool sites key by
   `pool_identity(entry, index) = index.get(identity, identity)` — a pure function of the text, so
   §5's two special cases hold by construction (suffix-minted support/core/node instance texts miss
   the index and keep multiplying; `*_enhancement_additional` still pools by stat key). SourceEntry
   also carries a stamped `pooling_uuid` (definition-level surfaces only) as metadata for the
   breakdown UI / locale future.
5. **Cross-checks for one season**: `tests/test_identity_crosscheck.py` (every stored uuid
   recomputes from its text — DELETE AT SS13, after which the scraper's freeze store is the source
   of truth) + the index-equivalence gate in `tests/test_pooling_partition.py` (fixture refrozen:
   175 identities / 298 texts; the 3 §5-ruled rewordings plus 3 corpus-source deltas, all
   scraper-confirmed).

Still English-keyed (deliberately deferred to the localization pass): the condition matcher
(`_COND_PATTERNS`, §4), `specific_rolls` keys (`affixIdentity.ts` — formatting-invariant, old
builds' rolls survive), and stat-key resolution (`mod_parser`). Keying the pooling layer on uuids is
the piece that had to move first; locale texts attach to the same uuids via `text_by_lang` later.
