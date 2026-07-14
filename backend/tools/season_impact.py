"""Engine-impact mapper — component F of the season-diff system.

.claude/plans/season-diff-system-spec.md §5 "F — Engine-impact mapper": the ONE builder-side
piece of a five-component system that otherwise lives entirely in the sibling `tlidb-crawler`
repo. F reads the crawler-produced `season-diff-<A>-<B>.json` artifact (component A, joined on
the frozen crawler `entity_uuid`/`pooling_uuid` identity layer) and maps every CHANGED entity
(verdict != "unchanged") onto the tlibuilder ENGINE code that models it, so a season transition
produces an instant "what engine code needs review" checklist instead of a manual hunt.

For each changed SKILL (activation_medium_skill / active_skill / support_skill /
magnificent_support_skill / noble_support_skill / passive_skill / modularization_skill):
    - Resolve its `item_id` via the LOCAL season catalog (`data/seasons/<season>/_skills.json`,
      identity-joined by `uuid` — the same uuid the crawler minted, so this is a direct dict
      lookup, no fuzzy matching). Prefers season_b's catalog (the target season, most likely to
      be on disk), falls back to season_a's.
    - Check `engine.skill_resolver._REGISTRY` for that item_id. A skill with NO registry entry
      computes `total_dps = 0.0` (see skill_resolver.py / CLAUDE.md) — so a newly-CHANGED skill
      with no entry is flagged NOT MODELED (no engine work possible/needed there yet); a changed
      skill WITH an entry is flagged RE-VERIFY (its coefficients likely drifted).
    - Cross-reference `data/verification/*.json` (`skills[]` arrays, matched by exact display
      name) — these entries may now describe stale numbers.
    - Cross-reference golden fixtures under `backend/tests/fixtures/**/*.json` (both by exact
      filename-slug match, e.g. `support_skill_golden/path_of_flames.json` for item_id
      `path_of_flames`, and by item_id/name substring inside composite baseline fixtures) —
      these are the goldens expected to move (additive-only per CLAUDE.md's golden discipline;
      a VALUE changing here is exactly the signal this tool exists to predict).

For each changed GEAR item (legendary_gear) — lighter touch per spec: no registry to check, just
list it, and flag any brand-new affix wording (an `added` line, or the `text_after` of a
`template_changed` line — NOT a `renumbered` line, which is the same wording with new numbers)
that `tools.audit_stat_coverage._resolve_craft_affix` can't resolve to a stat key, since that is
exactly "missing stats" — an affix the engine would otherwise silently ignore.

For each changed HERO_TRAIT — a "generic"-shaped type (the crawler's `season_diff` engine routes it
through a coarse recursive field-diff, `field_changes: [{path, before, after, status}]`, not the
skill/gear differs' `line_changes`/`variants`):
    - Resolve its `trait_id` via the LOCAL season catalog (`data/seasons/<season>/_hero_traits.json`,
      identity-joined by `uuid`, same shape as skills). Check `engine.hero_traits._APPLY` for that
      `trait_id`. UNLIKE skills, no bespoke module does NOT mean "not modeled" — most hero traits
      resolve fine through the generic mod_parser stat-line pipeline (see
      `engine/hero_traits/README.md`), so a `trait_id` with no module is flagged generic-resolved
      (spot-check new wording), never NOT MODELED; a `trait_id` WITH a module is flagged RE-VERIFY
      (its hand-coded coefficient arrays are literal season numbers baked into Python).
    - Cross-reference `data/verification/*.json` and golden fixtures the same way skills do (hero-
      trait verification entries already use the same `skills[]` field, e.g. `wind-stalker.json`).
Other generic-shaped types (`talent_tree`, `ethereal_prism`, `pactspirit`, ...) are NOT mapped yet —
see the "Not analyzed by this tool" section this renders; they have no per-entity registry to join
against the way hero_trait does (see `_KNOWN_GENERIC_TYPES`'s docstring).

Usage (from backend/):
    py -3.12 -m tools.season_impact <path-to-season-diff-A-B.json> [--out-dir DIR] [--season NAME]

Output (NOT written into data/ or a committed test dir — gitignored `.wolf/` by default, since
this is a generated report for the owner/engine/docs-scribe to read, not tracked source):
    <out-dir>/season-impact-<A>-<B>.json   — machine-readable per-entity mapping + summary
    <out-dir>/season-impact-<A>-<B>.md     — human-readable checklist

This is a thin CONSUMER of the crawler artifact — it does not modify `data/seasons/**`,
`data/verification/**`, or any golden fixture; it only reads them to build the report. It does
not touch the frozen `backend/build_code.py` codec.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_BACKEND)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from persistence import season_manager  # noqa: E402
from engine.skill_resolver import _REGISTRY as SKILL_REGISTRY  # noqa: E402
from engine.hero_traits import _APPLY as HERO_TRAIT_REGISTRY  # noqa: E402

# Skill-shaped season_diff types (mirrors tools/rebuild_skills.py's _SKILL_TYPE_DIRS — the set of
# skill_type values that live in _skills.json and are therefore uuid-resolvable against it).
_KNOWN_SKILL_TYPES = {
    "active_skill", "passive_skill", "support_skill",
    "noble_support_skill", "magnificent_support_skill",
    "activation_medium_skill", "modularization_skill",
}
_KNOWN_GEAR_TYPES = {"legendary_gear"}

# "Generic"-shaped season_diff types — everything the crawler's `season_diff` engine routes through
# its coarse recursive `diff_generic_entity` (field_changes: [{path, before, after, status}]) rather
# than the fine-grained skill/gear differs. `engine.hero_traits._APPLY` gives hero_trait a real
# per-entity registry to check (see _hero_trait_impact), so it's the first (and, as of this piece,
# ONLY) type wired here. talent_tree and ethereal_prism are DELIBERATELY not in this set yet — they
# have no per-entity registry to join against (core_talent_resolver.py / node_resolver.py /
# prism_core_talents.py are ~100% generic-text-parse pipelines, not uuid-keyed dispatch tables) and
# the crawler doesn't expose node-level identity in the diff artifact for talent_tree, so a handler
# for them needs a different (lower-confidence, text-resolves-or-not) shape — that's a separate
# piece. pactspirit is deliberately never planned here: no bespoke pact-spirit engine registry
# exists at all (the one bespoke minion module, `minion_effects/thunder_magus.py`, is keyed by a
# SKILL item_id and is already covered by the skill branch above).
_KNOWN_GENERIC_TYPES = {"hero_trait"}

_VERIFICATION_DIR = os.path.join(_REPO, "data", "verification")
_FIXTURES_DIR = os.path.join(_BACKEND, "tests", "fixtures")
_DEFAULT_OUT_DIR = os.path.join(_REPO, ".wolf", "season_impact")

_CHANGED_VERDICTS = {"renumbered", "reworked", "regrouped", "added", "removed"}
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("_", (name or "").lower()).strip("_")


# ── Local season catalog resolution (uuid -> item_id) ────────────────────────────────────────

def _load_catalog_maps(season_a: str, season_b: str) -> tuple[dict, dict, dict, str | None]:
    """Return (skills_uuid_map, gear_uuid_map, hero_traits_uuid_map, season_used). Tries season_b
    (the target season — most likely to be the currently-imported one) then season_a. None of the
    three maps depend on the season being ACTIVE (`data/seasons/.active`) — any imported season dir
    on disk works."""
    available = set(season_manager.list_seasons())
    for season in (season_b, season_a):
        if not season or season not in available:
            continue
        skills_data = season_manager.load_skills(season, raw=True)
        gear_data = season_manager.load_legendary_gear(season)
        hero_traits_data = season_manager.load_hero_traits(season, raw=True)
        if not skills_data and not gear_data and not hero_traits_data:
            continue
        skills_map = {}
        for sk in (skills_data or {}).get("skills", []):
            if sk.get("uuid"):
                skills_map[sk["uuid"]] = {
                    "item_id": sk.get("item_id"),
                    "name": sk.get("name"),
                    "skill_type": sk.get("skill_type"),
                }
        gear_map = {}
        for it in (gear_data or {}).get("items", []):
            if it.get("uuid"):
                gear_map[it["uuid"]] = {"item_id": it.get("item_id"), "name": it.get("name")}
        hero_traits_map = {}
        for tr in (hero_traits_data or {}).get("traits", []):
            if tr.get("uuid"):
                hero_traits_map[tr["uuid"]] = {
                    "trait_id": tr.get("trait_id"),
                    "hero": tr.get("hero"),
                    "variant_name": tr.get("variant_name"),
                }
        return skills_map, gear_map, hero_traits_map, season
    return {}, {}, {}, None


def _registry_scoped_skill_types(skills_uuid_map: dict) -> set[str]:
    """`skill_resolver._REGISTRY` is a per-skill dispatch table for skills with a hand-coded hit-
    form/DoT model — empirically (see skill_resolver.py) it currently only ever holds
    `active_skill`-typed entries (Berserking Blade, Chain Lightning, …). Passives, supports
    (standard/magnificent/noble), and activation mediums are modeled through entirely different
    GENERIC pipelines that don't need a per-skill registry entry at all:
      - support_skill / magnificent_support_skill / noble_support_skill -> `support_resolver.py`
        + `support_lines.py` (parses each support's own description lines generically).
      - activation_medium_skill -> `skill_effects/activation_medium.py` (roll parsing + wiring).
      - passive_skill -> heterogeneous: minion-summon passives go through
        `minion_offense.py`/`minion_effects/`, others through the generic stat-line pipeline.
    So `has_registry_entry=False` is only a meaningful "not modeled" signal for the skill_types
    the registry actually covers — for every other type it would ALWAYS be False and would be
    noise, not a finding. This computes that set empirically from the local season catalog
    (whichever skill_types the registry's item_ids actually resolve to) instead of hardcoding it,
    so a future season that (surprisingly) registers e.g. a passive still classifies correctly."""
    types: set[str] = set()
    for entry in skills_uuid_map.values():
        if entry.get("item_id") in SKILL_REGISTRY:
            skill_type = entry.get("skill_type")
            if skill_type:  # a catalog entry with no skill_type must never enter the set — a
                # bare None sorts against str and blows up render_markdown's sorted() call.
                types.add(skill_type)
    return types


# ── Verification DB index (name -> [verification ids]) ───────────────────────────────────────

def _load_verification_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    if not os.path.isdir(_VERIFICATION_DIR):
        return index
    for fn in sorted(os.listdir(_VERIFICATION_DIR)):
        if not fn.endswith(".json"):
            continue
        vid = os.path.splitext(fn)[0]
        with open(os.path.join(_VERIFICATION_DIR, fn), encoding="utf-8") as f:
            entry = json.load(f)
        for skill_name in entry.get("skills", []) or []:
            index.setdefault(skill_name.strip().lower(), []).append(vid)
    return index


# ── Golden fixture index ──────────────────────────────────────────────────────────────────────

def _load_fixture_index() -> dict[str, str]:
    """{relative_path: raw_text} for every JSON fixture under backend/tests/fixtures/."""
    index: dict[str, str] = {}
    if not os.path.isdir(_FIXTURES_DIR):
        return index
    for root, _dirs, files in os.walk(_FIXTURES_DIR):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            abspath = os.path.join(root, fn)
            relpath = os.path.relpath(abspath, _BACKEND).replace("\\", "/")
            with open(abspath, encoding="utf-8") as f:
                index[relpath] = f.read()
    return index


def _name_word_boundary_match(name: str, text: str) -> bool:
    """True if `name` appears in `text` as a whole run of characters, not merely embedded inside
    a longer unrelated word — a short/generic display name (e.g. "Storm") must not raw-substring
    match an unrelated golden whose text happens to contain it mid-word (e.g. "Firestorm Totem")."""
    if not name:
        return False
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def _matching_golden_files(
    fixture_index: dict[str, str], item_id: str | None, name_after: str, name_before: str
) -> list[str]:
    slugs = {s for s in (_slugify(name_after), _slugify(name_before)) if s}
    hits: set[str] = set()
    for relpath, text in fixture_index.items():
        stem = _slugify(os.path.splitext(os.path.basename(relpath))[0])
        if stem in slugs or (item_id and stem == item_id.lower()):
            hits.add(relpath)
            continue
        if item_id and f'"{item_id}"' in text:
            hits.add(relpath)
            continue
        if name_after and _name_word_boundary_match(name_after, text):
            hits.add(relpath)
    return sorted(hits)


# ── Type-shape sniffing (skill-shaped vs gear-shaped vs unknown) ─────────────────────────────

def _classify_type(type_name: str, type_block: dict) -> str:
    entities = type_block.get("entities") or {}
    for e in entities.values():
        if "variants" in e:
            return "gear"
        if "line_changes" in e:
            return "skill"
        if "field_changes" in e:
            # The generic shape is shared by EVERY type diff_generic_entity handles (hero_trait,
            # talent_tree, ethereal_prism, pactspirit, craft_base_type, ...) — gate on
            # _KNOWN_GENERIC_TYPES (an explicit allowlist, not shape alone) so a type this tool has
            # no registry/join for (e.g. pactspirit) still falls through to "unknown" instead of
            # silently getting a hollow "generic impact" section with nothing to say.
            return "generic" if type_name in _KNOWN_GENERIC_TYPES else "unknown"
    if type_name in _KNOWN_GEAR_TYPES:
        return "gear"
    if type_name in _KNOWN_SKILL_TYPES:
        return "skill"
    if type_name in _KNOWN_GENERIC_TYPES:
        return "generic"
    return "unknown"


# ── Skill impact ───────────────────────────────────────────────────────────────────────────────

def _skill_impact(
    entity_type: str, uuid: str, entity: dict,
    skills_uuid_map: dict, registry_scoped_types: set[str],
    verification_index: dict, fixture_index: dict,
    catalog_available: bool = True,
) -> dict:
    name_after = entity.get("name_after") or entity.get("name_before") or uuid
    name_before = entity.get("name_before") or name_after
    catalog = skills_uuid_map.get(uuid)
    item_id = catalog["item_id"] if catalog else None

    if not catalog_available:
        # NEITHER season catalog is on disk. `registry_scoped_types` is then computed from an
        # empty skills_uuid_map and comes back the EMPTY set — applying the registry-scope gate
        # in that state would make registry_applicable False for EVERY changed skill, including
        # genuinely registry-modeled active_skills, and they'd be falsely bucketed as "outside
        # the registry's scope" (see .wolf/buglog.json). Don't guess: surface this as its own
        # unresolved state instead of computing (or faking) a modeled/not-modeled verdict.
        registry_applicable = None
        has_registry_entry = None
        registry_module = None
        registry_function = None
        resolution = "unresolved_no_catalog"
    else:
        registry_applicable = entity_type in registry_scoped_types

        if not registry_applicable:
            # This skill_type isn't one skill_resolver._REGISTRY ever dispatches (see
            # _registry_scoped_skill_types) — a False registry lookup here would be noise, not a
            # finding, so we deliberately don't compute has_registry_entry for it.
            has_registry_entry = None
            registry_module = None
            registry_function = None
            resolution = "not_registry_scoped"
        elif item_id is not None:
            has_registry_entry = item_id in SKILL_REGISTRY
            fn = SKILL_REGISTRY.get(item_id)
            registry_module = fn.__module__ if fn else None
            registry_function = fn.__qualname__ if fn else None
            resolution = "resolved"
        else:
            has_registry_entry = None  # unknown — no local catalog entry to check against
            registry_module = None
            registry_function = None
            resolution = "unresolved_no_catalog_entry"

    verification_ids = sorted(set(
        verification_index.get(name_after.strip().lower(), [])
        + verification_index.get(name_before.strip().lower(), [])
    ))
    golden_files = _matching_golden_files(fixture_index, item_id, name_after, name_before)

    line_changes = entity.get("line_changes") or {}
    line_change_counts = {
        k: (len(v) if isinstance(v, list) else v)
        for k, v in line_changes.items()
    }

    return {
        "uuid": uuid,
        "skill_type": entity_type,
        "name": name_after,
        "name_before": name_before if name_before != name_after else None,
        "verdict": entity["verdict"],
        "item_id": item_id,
        "resolution": resolution,
        "registry_applicable": registry_applicable,
        "has_registry_entry": has_registry_entry,
        "registry_module": registry_module,
        "registry_function": registry_function,
        "verification_ids": verification_ids,
        "golden_files": golden_files,
        "scalar_changes": entity.get("scalar_changes") or {},
        "line_change_counts": line_change_counts,
        "has_localization_mismatch": bool(entity.get("has_localization_mismatch")),
    }


# ── Localization-mismatch-only entities ───────────────────────────────────────────────────────

def _localization_mismatch_impact(entity_type: str, uuid: str, entity: dict) -> dict:
    """An entity whose ONLY finding is a `localization_mismatch`. The crawler deliberately keeps
    its verdict as `"unchanged"` for these (a CJK crawl leak masks whether the content actually
    changed — see the sibling crawler repo's season_diff engine), so `_CHANGED_VERDICTS` never
    selects them and they'd otherwise silently vanish from this report even though the underlying
    skill/gear might be genuinely changed. Route them to their own re-crawl bucket instead of
    running them through the normal modeled/not-modeled logic — their diff is untrustworthy."""
    name_after = entity.get("name_after") or entity.get("name_before") or uuid
    name_before = entity.get("name_before") or name_after
    return {
        "uuid": uuid,
        "entity_type": entity_type,
        "name": name_after,
        "name_before": name_before if name_before != name_after else None,
        "verdict": entity.get("verdict"),
    }


# ── Gear impact ────────────────────────────────────────────────────────────────────────────────

def _collect_new_wording(entity: dict) -> list[dict]:
    """Genuinely NEW affix wording: `added` lines and the `text_after` of `template_changed`
    lines (non-numeric text differs). Explicitly excludes `renumbered` (same wording, new
    numbers only) and `cosmetic`/`regrouped` (formatting-only)."""
    out: list[dict] = []

    def _from_line_changes(source: str, lc: dict) -> None:
        for entry in lc.get("added", []):
            out.append({"source": source, "kind": "added", "modifier_id": entry.get("modifier_id"),
                        "text": entry.get("text")})
        for entry in lc.get("template_changed", []):
            out.append({"source": source, "kind": "template_changed", "modifier_id": entry.get("modifier_id"),
                        "text": entry.get("text_after")})

    for variant in entity.get("variants") or []:
        if variant.get("status") != "compared":
            continue
        _from_line_changes(f"variant:{variant.get('rarity_state')}", variant.get("line_changes") or {})
    for slot in entity.get("random_affixes") or []:
        if slot.get("status") != "compared":
            continue
        _from_line_changes(
            f"random_affix:{slot.get('rarity_state')}/{slot.get('placeholder')}",
            slot.get("line_changes") or {},
        )
    return out


def _gear_impact(uuid: str, entity: dict, gear_uuid_map: dict, resolve_affix) -> dict:
    name_after = entity.get("name_after") or entity.get("name_before") or uuid
    name_before = entity.get("name_before") or name_after
    catalog = gear_uuid_map.get(uuid)
    item_id = catalog["item_id"] if catalog else None

    new_wording = _collect_new_wording(entity)
    for w in new_wording:
        w["resolved"] = bool(resolve_affix(w["text"])) if w.get("text") else False
    unresolved = [w for w in new_wording if not w["resolved"]]

    variants_added = sum(1 for v in entity.get("variants") or [] if v.get("status") == "variant_added")
    variants_removed = sum(1 for v in entity.get("variants") or [] if v.get("status") == "variant_removed")

    return {
        "uuid": uuid,
        "name": name_after,
        "name_before": name_before if name_before != name_after else None,
        "verdict": entity["verdict"],
        "item_id": item_id,
        "variants_added": variants_added,
        "variants_removed": variants_removed,
        "new_affix_texts": new_wording,
        "new_affix_unresolved": unresolved,
        "has_localization_mismatch": bool(entity.get("has_localization_mismatch")),
    }


# ── Hero-trait impact (generic-shaped) ────────────────────────────────────────────────────────

def _hero_trait_impact(
    uuid: str, entity: dict, hero_traits_uuid_map: dict,
    verification_index: dict, fixture_index: dict,
    catalog_available: bool = True,
) -> dict:
    """Mirrors `_skill_impact`'s uuid -> local-catalog -> registry join, but keyed on `trait_id`
    against `engine.hero_traits._APPLY` instead of `item_id` against `skill_resolver._REGISTRY`,
    and reading the coarse `field_changes` shape `diff_generic_entity` produces instead of
    `line_changes`.

    Unlike skills, `has_module=False` is NOT a "not modeled" signal: a hero trait with no bespoke
    `engine/hero_traits/` module is still resolved through the SAME generic mod_parser stat-line
    pipeline gear/talent text uses (see `engine/hero_traits/README.md`) — most of the ~26 trait
    variants in `_hero_traits.json` have no bespoke module and work fine. So this only ever reports
    two asymmetric-confidence buckets for a resolved trait: `has_module=True` -> RE-VERIFY (its
    hand-coded coefficient arrays, e.g. lightning_shadow.py's `_BASE_ADDITIONAL`, are literally
    season numbers baked into Python and drift on a renumber); `has_module=False` -> a much weaker
    "generic-resolved, spot-check new/changed wording still parses" signal, never "not modeled".
    """
    name_after = entity.get("name_after") or entity.get("name_before") or uuid
    name_before = entity.get("name_before") or name_after
    catalog = hero_traits_uuid_map.get(uuid)
    trait_id = catalog["trait_id"] if catalog else None
    hero = catalog["hero"] if catalog else None

    if not catalog_available:
        # Same "don't guess" stance as _skill_impact's catalog_available branch — neither season's
        # local catalog is on disk, so trait_id (and therefore the registry check) can't be
        # computed at all. Surface as its own unresolved state rather than faking a verdict.
        has_module = None
        registry_module = None
        registry_function = None
        resolution = "unresolved_no_catalog"
    elif trait_id is not None:
        has_module = trait_id in HERO_TRAIT_REGISTRY
        fn = HERO_TRAIT_REGISTRY.get(trait_id)
        registry_module = fn.__module__ if fn else None
        registry_function = fn.__qualname__ if fn else None
        resolution = "resolved"
    else:
        has_module = None  # unknown — no local catalog entry to check against
        registry_module = None
        registry_function = None
        resolution = "unresolved_no_catalog_entry"

    verification_ids = sorted(set(
        verification_index.get(name_after.strip().lower(), [])
        + verification_index.get(name_before.strip().lower(), [])
    ))
    # Hero-trait tests (backend/tests/test_<trait>.py) are inline pytest assertions, not JSON
    # golden fixtures under backend/tests/fixtures/ — an EMPTY golden_files list here is the
    # expected, correct outcome for every hero trait, not a sign the match logic is broken.
    golden_files = _matching_golden_files(fixture_index, trait_id, name_after, name_before)

    field_changes = entity.get("field_changes") or []

    return {
        "uuid": uuid,
        "entity_type": "hero_trait",
        "name": name_after,
        "name_before": name_before if name_before != name_after else None,
        "hero": hero,
        "verdict": entity["verdict"],
        "trait_id": trait_id,
        "resolution": resolution,
        "has_module": has_module,
        "registry_module": registry_module,
        "registry_function": registry_function,
        "verification_ids": verification_ids,
        "golden_files": golden_files,
        "field_change_count": len(field_changes),
        "has_localization_mismatch": bool(entity.get("has_localization_mismatch")),
    }


# ── Main run ───────────────────────────────────────────────────────────────────────────────────

def run_impact(diff_path: str, season_override: str | None = None) -> dict:
    with open(diff_path, encoding="utf-8") as f:
        diff = json.load(f)

    season_a = diff.get("season_a")
    season_b = diff.get("season_b")
    if season_override:
        skills_uuid_map, gear_uuid_map, hero_traits_uuid_map, catalog_season_used = _load_catalog_maps(
            season_override, season_override
        )
    else:
        skills_uuid_map, gear_uuid_map, hero_traits_uuid_map, catalog_season_used = _load_catalog_maps(
            season_a, season_b
        )

    verification_index = _load_verification_index()
    fixture_index = _load_fixture_index()
    registry_scoped_types = _registry_scoped_skill_types(skills_uuid_map)
    # Neither season's catalog was found on disk — see _skill_impact's `catalog_available` branch:
    # the registry-scope gate must NOT be applied when it can't be computed for anything.
    catalog_available = catalog_season_used is not None

    # Deferred import — mirrors tools/audit_stat_coverage.py's own lazy `from server import …`
    # (avoids importing the FastAPI app at module load for callers who never touch gear).
    from tools.audit_stat_coverage import _resolve_craft_affix

    skills: list[dict] = []
    gear: list[dict] = []
    generic: list[dict] = []
    localization_mismatches: list[dict] = []
    types_no_baseline: dict[str, dict] = {}
    types_skipped_unknown: list[str] = []

    for type_name, type_block in diff.get("types", {}).items():
        if type_block.get("no_historical_baseline"):
            types_no_baseline[type_name] = {
                "present_in": type_block.get("present_in"),
                "entity_count": type_block.get("entity_count"),
            }
            continue

        category = _classify_type(type_name, type_block)
        entities = type_block.get("entities") or {}
        changed = {u: e for u, e in entities.items() if e.get("verdict") in _CHANGED_VERDICTS}
        # The crawler deliberately keeps verdict="unchanged" for a localization-mismatch-only
        # finding (a CJK crawl leak masks whether content actually changed), so these are
        # invisible to `_CHANGED_VERDICTS` above — select them separately so they don't vanish.
        loc_mismatch_only = {
            u: e for u, e in entities.items()
            if e.get("verdict") == "unchanged" and e.get("has_localization_mismatch")
        }
        for uuid, entity in loc_mismatch_only.items():
            localization_mismatches.append(_localization_mismatch_impact(type_name, uuid, entity))

        if category == "skill":
            for uuid, entity in changed.items():
                skills.append(_skill_impact(
                    type_name, uuid, entity, skills_uuid_map, registry_scoped_types,
                    verification_index, fixture_index, catalog_available=catalog_available,
                ))
        elif category == "gear":
            for uuid, entity in changed.items():
                gear.append(_gear_impact(uuid, entity, gear_uuid_map, _resolve_craft_affix))
        elif category == "generic":
            # Only hero_trait is wired to _KNOWN_GENERIC_TYPES so far — a future generic type (e.g.
            # talent_tree, ethereal_prism) needs its own branch here (different catalog, different
            # join, no registry to check), not a fallthrough onto _hero_trait_impact's shape.
            if type_name == "hero_trait":
                for uuid, entity in changed.items():
                    generic.append(_hero_trait_impact(
                        uuid, entity, hero_traits_uuid_map,
                        verification_index, fixture_index, catalog_available=catalog_available,
                    ))
        else:
            types_skipped_unknown.append(type_name)

    registry_scoped = [s for s in skills if s["resolution"] == "resolved"]
    modeled = [s for s in registry_scoped if s["has_registry_entry"] is True]
    not_modeled = [s for s in registry_scoped if s["has_registry_entry"] is False]
    unresolved = [s for s in skills if s["resolution"] == "unresolved_no_catalog_entry"]
    not_registry_scoped = [s for s in skills if s["resolution"] == "not_registry_scoped"]
    unresolved_catalog_missing = [s for s in skills if s["resolution"] == "unresolved_no_catalog"]
    removed = [s for s in skills if s["verdict"] == "removed"]

    hero_traits_resolved = [t for t in generic if t["entity_type"] == "hero_trait" and t["resolution"] == "resolved"]
    hero_traits_bespoke = [t for t in hero_traits_resolved if t["has_module"] is True]
    hero_traits_generic_resolved = [t for t in hero_traits_resolved if t["has_module"] is False]
    hero_traits_unresolved = [
        t for t in generic if t["entity_type"] == "hero_trait" and t["resolution"] == "unresolved_no_catalog_entry"
    ]
    hero_traits_unresolved_catalog_missing = [
        t for t in generic if t["entity_type"] == "hero_trait" and t["resolution"] == "unresolved_no_catalog"
    ]
    hero_traits_removed = [t for t in generic if t["entity_type"] == "hero_trait" and t["verdict"] == "removed"]

    verification_ids_touched = sorted({
        vid for s in skills for vid in s["verification_ids"]
    } | {
        vid for t in generic for vid in t["verification_ids"]
    })
    golden_files_touched = sorted({
        g for s in skills for g in s["golden_files"]
    } | {
        g for t in generic for g in t["golden_files"]
    })
    gear_with_new_text = [g for g in gear if g["new_affix_texts"]]
    gear_unresolved = [g for g in gear if g["new_affix_unresolved"]]

    summary = {
        "changed_skills_total": len(skills),
        "changed_skills_registry_scoped_types": sorted(registry_scoped_types),
        "changed_skills_modeled": len(modeled),
        "changed_skills_not_modeled": len(not_modeled),
        "changed_skills_unresolved_no_catalog": len(unresolved),
        "changed_skills_not_registry_scoped": len(not_registry_scoped),
        "changed_skills_removed": len(removed),
        "catalog_missing": not catalog_available,
        "changed_skills_unresolved_catalog_missing": len(unresolved_catalog_missing),
        "verification_entries_touched": verification_ids_touched,
        "golden_files_likely_to_move": golden_files_touched,
        "changed_gear_total": len(gear),
        "changed_gear_with_new_affix_text": len(gear_with_new_text),
        "changed_gear_new_affix_unresolved": len(gear_unresolved),
        "changed_hero_traits_total": len(hero_traits_resolved) + len(hero_traits_unresolved)
        + len(hero_traits_unresolved_catalog_missing),
        "changed_hero_traits_bespoke_reverify": len(hero_traits_bespoke),
        "changed_hero_traits_generic_resolved": len(hero_traits_generic_resolved),
        "changed_hero_traits_unresolved_no_catalog": len(hero_traits_unresolved),
        "changed_hero_traits_unresolved_catalog_missing": len(hero_traits_unresolved_catalog_missing),
        "changed_hero_traits_removed": len(hero_traits_removed),
        "types_with_no_historical_baseline": types_no_baseline,
        "types_skipped_unknown_shape": types_skipped_unknown,
        "localization_mismatch_entities_total": len(localization_mismatches),
    }

    return {
        "season_a": season_a,
        "season_b": season_b,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": os.path.abspath(diff_path),
        "catalog_season_used": catalog_season_used,
        "summary": summary,
        "skills": skills,
        "gear": gear,
        "generic": generic,
        "localization_mismatches": localization_mismatches,
    }


# ── Markdown rendering ────────────────────────────────────────────────────────────────────────

def render_markdown(report: dict) -> str:
    s = report["summary"]
    a, b = report["season_a"], report["season_b"]
    lines = [f"# Engine impact — {a} -> {b}", ""]

    if s.get("catalog_missing"):
        lines += [
            "## WARNING: season catalog not on disk",
            "",
            "Neither season's local catalog (`data/seasons/<season>/_skills.json` / "
            "`_legendary_gear.json` / `_hero_traits.json`) was found. The `skill_resolver._REGISTRY`- "
            "and `hero_traits._APPLY`-scope gates could NOT be evaluated for a single changed skill "
            "or hero trait below — every one is bucketed `unresolved_no_catalog` rather than "
            "modeled/not-modeled, since guessing would risk flagging genuinely registry-modeled "
            "skills/traits (e.g. an `active_skill`, or a trait like Lightning Shadow) as \"not "
            "modeled\". **Import the season locally and re-run this tool** before trusting any "
            "modeled/not-modeled verdict in this report.",
            "",
        ]

    lines += [
        f"Generated {report['generated_at']} from `{report['source_artifact']}`.",
        f"Local season catalog used for uuid resolution: `{report['catalog_season_used'] or '(none found — item_id/registry lookups unresolved)'}`.",
        "",
        "## Summary",
        "",
    ]

    if s.get("catalog_missing"):
        lines.append(
            f"- **{s['changed_skills_total']}** changed skills — engine-modeling status UNKNOWN "
            f"for all of them (season catalog not on disk; see warning above). "
            f"**{s['changed_skills_removed']}** more were removed entirely (a GLOBAL count across "
            f"ALL changed-skill types, not scoped to the registry-gate figures above)."
        )
    else:
        lines.append(
            f"- **{s['changed_skills_total']}** changed skills — of the "
            f"{s['changed_skills_modeled'] + s['changed_skills_not_modeled'] + s['changed_skills_unresolved_no_catalog']} "
            f"in a `skill_resolver._REGISTRY`-scoped type ({', '.join(s['changed_skills_registry_scoped_types']) or 'none'}): "
            f"**{s['changed_skills_modeled']}** modeled (registry entry -> RE-VERIFY), "
            f"**{s['changed_skills_not_modeled']}** NOT modeled (no registry entry), "
            f"**{s['changed_skills_unresolved_no_catalog']}** unresolved (no local catalog entry). "
            f"**{s['changed_skills_not_registry_scoped']}** more are outside the registry's scope entirely "
            f"(supports/passives/activation-mediums — modeled, if at all, via other generic subsystems; see below). "
            f"Separately, **{s['changed_skills_removed']}** more were removed entirely (a GLOBAL count "
            f"across ALL changed-skill types, not scoped to the \"outside the registry's scope\" figure "
            f"just above)."
        )

    lines += [
        f"- **{len(s['verification_entries_touched'])}** verification entries reference a changed skill — review for staleness.",
        f"- **{len(s['golden_files_likely_to_move'])}** golden fixtures likely to move.",
        f"- **{s['changed_gear_total']}** changed gear items, **{s['changed_gear_with_new_affix_text']}** "
        f"introduce new affix wording, **{s['changed_gear_new_affix_unresolved']}** of those have text "
        f"`mod_parser` cannot currently resolve to a stat key.",
        f"- **{s['changed_hero_traits_total']}** changed hero traits — **{s['changed_hero_traits_bespoke_reverify']}** "
        f"have a bespoke `engine/hero_traits/` module (RE-VERIFY — hand-coded coefficients likely drifted), "
        f"**{s['changed_hero_traits_generic_resolved']}** have none (generic mod_parser pipeline — spot-check "
        f"new/changed wording, NOT a \"not modeled\" signal), **{s['changed_hero_traits_unresolved_no_catalog']}** "
        f"unresolved (no local catalog entry). Separately, **{s['changed_hero_traits_removed']}** more were "
        f"removed entirely.",
    ]
    if s.get("localization_mismatch_entities_total"):
        lines.append(
            f"- **{s['localization_mismatch_entities_total']}** entities have ONLY a "
            f"localization-mismatch finding (verdict stayed `unchanged`) — untrustworthy diff, "
            f"needs re-crawl before impact can be judged; see below."
        )
    lines.append("")

    if s["verification_entries_touched"]:
        lines += ["## Verification entries to review", ""]
        for vid in s["verification_entries_touched"]:
            lines.append(f"- `data/verification/{vid}.json`")
        lines.append("")

    if s["golden_files_likely_to_move"]:
        lines += ["## Goldens likely to move", ""]
        for gpath in s["golden_files_likely_to_move"]:
            lines.append(f"- `backend/{gpath}`")
        lines.append("")

    lines += ["## Changed skills — RE-VERIFY (has a registry entry)", ""]
    for sk in sorted(
        [x for x in report["skills"] if x["resolution"] == "resolved" and x["has_registry_entry"] is True],
        key=lambda x: x["name"],
    ):
        lines.append(
            f"- **{sk['name']}** (`{sk['item_id']}`, {sk['skill_type']}, verdict={sk['verdict']}) "
            f"-> `{sk['registry_module']}::{sk['registry_function']}`"
        )
        if sk["verification_ids"]:
            lines.append(f"  - verification: {', '.join(sk['verification_ids'])}")
        if sk["golden_files"]:
            lines.append(f"  - goldens: {', '.join(sk['golden_files'])}")
    lines.append("")

    lines += ["## Changed skills — NOT MODELED (registry-scoped type, no registry entry)", ""]
    for sk in sorted(
        [x for x in report["skills"] if x["resolution"] == "resolved" and x["has_registry_entry"] is False],
        key=lambda x: x["name"],
    ):
        lines.append(f"- **{sk['name']}** (`{sk['item_id']}`, {sk['skill_type']}, verdict={sk['verdict']})")
    lines.append("")

    unresolved_skills = [x for x in report["skills"] if x["resolution"] == "unresolved_no_catalog_entry"]
    if unresolved_skills:
        lines += ["## Changed skills — unresolved (no local season catalog entry)", ""]
        for sk in sorted(unresolved_skills, key=lambda x: x["name"]):
            lines.append(f"- **{sk['name']}** ({sk['skill_type']}, verdict={sk['verdict']}, uuid=`{sk['uuid']}`)")
        lines.append("")

    catalog_missing_skills = [x for x in report["skills"] if x["resolution"] == "unresolved_no_catalog"]
    if catalog_missing_skills:
        lines += [
            "## Changed skills — unresolved (season catalog not on disk)", "",
            "The registry-scope gate could not be evaluated at all for these (see the WARNING "
            "at the top of this report) — no modeled/not-modeled/scope verdict is given.", "",
        ]
        for sk in sorted(catalog_missing_skills, key=lambda x: x["name"]):
            lines.append(f"- **{sk['name']}** ({sk['skill_type']}, verdict={sk['verdict']}, uuid=`{sk['uuid']}`)")
        lines.append("")

    not_scoped_skills = [x for x in report["skills"] if x["resolution"] == "not_registry_scoped"]
    if not_scoped_skills:
        lines += [
            "## Changed skills — outside skill_resolver._REGISTRY's scope", "",
            "Supports (`support_skill`/`magnificent_support_skill`/`noble_support_skill` — modeled "
            "generically by `support_resolver.py`/`support_lines.py`, no per-skill registry entry "
            "needed), activation mediums (`skill_effects/activation_medium.py`), and passives "
            "(heterogeneous — minion summons via `minion_offense.py`/`minion_effects/`, others via "
            "the generic stat-line pipeline). `has_registry_entry` is not a meaningful signal for "
            "these types, so no modeled/not-modeled verdict is given — only cross-references.", "",
        ]
        for sk in sorted(not_scoped_skills, key=lambda x: x["name"]):
            extra = []
            if sk["verification_ids"]:
                extra.append(f"verification: {', '.join(sk['verification_ids'])}")
            if sk["golden_files"]:
                extra.append(f"goldens: {', '.join(sk['golden_files'])}")
            suffix = f" — {'; '.join(extra)}" if extra else ""
            lines.append(f"- **{sk['name']}** ({sk['skill_type']}, verdict={sk['verdict']}){suffix}")
        lines.append("")

    if report["gear"]:
        lines += ["## Changed gear", ""]
        for g in sorted(report["gear"], key=lambda x: x["name"]):
            flag = ""
            if g["new_affix_unresolved"]:
                flag = f" — **{len(g['new_affix_unresolved'])} new affix line(s) unresolved by mod_parser**"
            elif g["new_affix_texts"]:
                flag = f" — {len(g['new_affix_texts'])} new affix line(s) (all resolve)"
            lines.append(f"- **{g['name']}** (`{g['item_id']}`, verdict={g['verdict']}){flag}")
            for w in g["new_affix_unresolved"]:
                lines.append(f"  - UNRESOLVED [{w['source']}/{w['kind']}]: {w['text']}")
        lines.append("")

    hero_traits = [x for x in report["generic"] if x["entity_type"] == "hero_trait"]

    reverify_traits = [x for x in hero_traits if x["resolution"] == "resolved" and x["has_module"] is True]
    if reverify_traits:
        lines += ["## Changed hero traits — RE-VERIFY (has a bespoke engine module)", ""]
        for tr in sorted(reverify_traits, key=lambda x: x["name"]):
            lines.append(
                f"- **{tr['name']}** (`{tr['trait_id']}`, {tr['hero']}, verdict={tr['verdict']}) "
                f"-> `{tr['registry_module']}::{tr['registry_function']}`"
            )
            if tr["verification_ids"]:
                lines.append(f"  - verification: {', '.join(tr['verification_ids'])}")
            if tr["golden_files"]:
                lines.append(f"  - goldens: {', '.join(tr['golden_files'])}")
        lines.append("")

    generic_resolved_traits = [x for x in hero_traits if x["resolution"] == "resolved" and x["has_module"] is False]
    if generic_resolved_traits:
        lines += [
            "## Changed hero traits — generic-resolved (no bespoke module)", "",
            "No `engine/hero_traits/` module owns these — they resolve through the SAME generic "
            "mod_parser stat-line pipeline gear/talent text uses, which is normal for most hero "
            "traits (see `engine/hero_traits/README.md`). This is NOT a \"not modeled\" finding; "
            "spot-check that the new/changed wording still parses the way it used to.", "",
        ]
        for tr in sorted(generic_resolved_traits, key=lambda x: x["name"]):
            extra = []
            if tr["verification_ids"]:
                extra.append(f"verification: {', '.join(tr['verification_ids'])}")
            if tr["golden_files"]:
                extra.append(f"goldens: {', '.join(tr['golden_files'])}")
            suffix = f" — {'; '.join(extra)}" if extra else ""
            lines.append(f"- **{tr['name']}** (`{tr['trait_id']}`, {tr['hero']}, verdict={tr['verdict']}){suffix}")
        lines.append("")

    unresolved_traits = [x for x in hero_traits if x["resolution"] == "unresolved_no_catalog_entry"]
    if unresolved_traits:
        lines += ["## Changed hero traits — unresolved (no local season catalog entry)", ""]
        for tr in sorted(unresolved_traits, key=lambda x: x["name"]):
            lines.append(f"- **{tr['name']}** (verdict={tr['verdict']}, uuid=`{tr['uuid']}`)")
        lines.append("")

    catalog_missing_traits = [x for x in hero_traits if x["resolution"] == "unresolved_no_catalog"]
    if catalog_missing_traits:
        lines += [
            "## Changed hero traits — unresolved (season catalog not on disk)", "",
            "The bespoke-module gate could not be evaluated at all for these (see the WARNING "
            "at the top of this report) — no RE-VERIFY/generic-resolved verdict is given.", "",
        ]
        for tr in sorted(catalog_missing_traits, key=lambda x: x["name"]):
            lines.append(f"- **{tr['name']}** (verdict={tr['verdict']}, uuid=`{tr['uuid']}`)")
        lines.append("")

    if report["localization_mismatches"]:
        lines += [
            "## Localization mismatch — needs re-crawl before impact can be judged", "",
            "These entities' crawler verdict stayed `unchanged` ONLY because a localization "
            "mismatch (a CJK crawl leak) masks whether the underlying content actually changed — "
            "the diff for them is untrustworthy. Not run through modeled/not-modeled logic; "
            "re-crawl the entity, then re-run this tool.", "",
        ]
        for loc in sorted(report["localization_mismatches"], key=lambda x: x["name"]):
            lines.append(f"- **{loc['name']}** ({loc['entity_type']}, uuid=`{loc['uuid']}`)")
        lines.append("")

    if s["types_with_no_historical_baseline"]:
        lines += ["## Types with no historical baseline (skipped — nothing to compare)", ""]
        for t, info in s["types_with_no_historical_baseline"].items():
            lines.append(f"- {t}: present only in {info['present_in']} ({info['entity_count']} entities)")
        lines.append("")

    if s["types_skipped_unknown_shape"]:
        lines += [
            "## Not analyzed by this tool (unrecognized entity shape) — review manually", "",
            "Entity types outside skill/gear/hero_trait scope. `talent_tree` "
            "(`backend/engine/core_talent_resolver.py`/`node_resolver.py`) and `ethereal_prism` "
            "(`backend/engine/prism_core_talents.py`) are ~100% generic-text-parse pipelines with no "
            "per-entity registry to check yet, and the crawler doesn't expose node-level identity "
            "for talent_tree — not yet mapped here (planned as a lower-confidence, separate piece). "
            "`pactspirit` has NO bespoke engine registry at all — its one real bespoke-minion "
            "mechanic (`engine/minion_effects/thunder_magus.py`) is keyed by a SKILL item_id and is "
            "already covered by the skill sections above, so it's never planned here. "
            "`craft_base_type`/`destiny`/`divinity_slate`/`hero_memories`/`memory_revival`/"
            "`tower_sequence`/`graft`/`blending_rituals` are pure data with no bespoke engine code. "
            "Review each manually.", "",
        ]
        for t in s["types_skipped_unknown_shape"]:
            lines.append(f"- {t}")
        lines.append("")

    return "\n".join(lines) + "\n"


# ── CLI ────────────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("diff_path", help="Path to a season-diff-<A>-<B>.json artifact (from the crawler's season_diff tool).")
    parser.add_argument("--out-dir", default=_DEFAULT_OUT_DIR, help=f"Output directory (default: {_DEFAULT_OUT_DIR}).")
    parser.add_argument("--season", default=None, help="Force a specific local season catalog for uuid resolution (default: try season_b then season_a from the diff artifact).")
    args = parser.parse_args()

    report = run_impact(args.diff_path, season_override=args.season)
    os.makedirs(args.out_dir, exist_ok=True)

    a, b = report["season_a"], report["season_b"]
    json_path = os.path.join(args.out_dir, f"season-impact-{a}-{b}.json")
    md_path = os.path.join(args.out_dir, f"season-impact-{a}-{b}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    s = report["summary"]
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(
        f"{s['changed_skills_total']} changed skills "
        f"({s['changed_skills_modeled']} modeled / {s['changed_skills_not_modeled']} not modeled / "
        f"{s['changed_skills_unresolved_no_catalog']} unresolved / {s['changed_skills_removed']} removed), "
        f"{len(s['verification_entries_touched'])} verification entries touched, "
        f"{len(s['golden_files_likely_to_move'])} goldens likely to move, "
        f"{s['changed_gear_total']} changed gear ({s['changed_gear_new_affix_unresolved']} with unresolved new affix text), "
        f"{s['changed_hero_traits_total']} changed hero traits "
        f"({s['changed_hero_traits_bespoke_reverify']} RE-VERIFY / "
        f"{s['changed_hero_traits_generic_resolved']} generic-resolved / "
        f"{s['changed_hero_traits_removed']} removed)."
    )


if __name__ == "__main__":
    main()
