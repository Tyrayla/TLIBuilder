"""Authoritative skill-data corrections for crawler-mangled entries.

Some skills import with garbled text (the crawler merges templated value clauses across lines). Rather than edit
the imported season JSON in place (which the next import would overwrite), we patch the loaded skills dict here.

Each override is keyed by skill_id and records:
  - authored_season: the season the correction was validated against,
  - expects_contains: a snippet of the ORIGINAL (wrong) text, so we can detect when a later import CHANGES the line
    (the bug got fixed, or the values changed) and the override must be re-validated by hand,
  - the corrected `detailed_description` / `simple_description` (Lv20 source-of-truth + Lv1 anchor).

apply_skill_overrides() patches the dict in place and returns review warnings:
  - if the expected corrupted snippet is GONE → the source changed → we DO NOT apply (the data may now be correct or
    different); flag for manual review instead of silently re-breaking it,
  - if the active season differs from authored_season → still apply (best effort), and flag for manual
    re-validation ONLY if the active season's raw skill data actually diverges (at the ranks/fields the override
    reads or modifies) from the authored-season data it was validated against. If the new season's raw data is
    identical where the two overlap, the override is still correct and the warning is suppressed — a season bump
    with unchanged underlying values shouldn't cry wolf. Divergence is checked on the NUMERIC content of each
    field (ignoring cosmetic formatting drift like a stray '+' prefix) so trivial crawler-text noise doesn't read
    as a real value change.
"""
from __future__ import annotations

import re

# skill_id → override spec. Values are the in-game truth (Lv20 detailed, Lv1 simple). Both Mana Boil effects scale
# with Empower Effect (it's an Empower skill) — that scaling is applied downstream by apply_empower_buffs, so the
# numbers here are the UNSCALED base values.
SKILL_OVERRIDES: dict[str, dict] = {
    "mana_boil": {
        "authored_season": "SS12",
        "reason": ("Crawler merged the consume clause into the Spell Damage clause "
                   "('Consumes 16.65 % additional Spell Damage while the skill lasts Mana every second'). "
                   "Truth: consume is 3% of Max Mana every second at ALL ranks; Euphoria is +16.65% additional "
                   "Spell Damage at Lv20 (10% at Lv1, 17% at Lv21). Both scale with Empower Effect."),
        "expects_contains": "Consumes 16.65 % additional Spell Damage",
        "detailed_description": [
            "Gains Euphoria upon casting the skill:",
            "16.65 % additional Spell Damage while the skill lasts",
            "Consumes 3 % of Max Mana every second",
            "Loses the Euphoria effect when Mana drops to 0.",
        ],
        "simple_description": [
            "Gains Euphoria upon casting the skill:",
            "10 % additional Spell Damage while the skill lasts",
            "Consumes 3 % of Max Mana every second",
            "Loses the Euphoria effect when Mana drops to 0.",
        ],
    },
}


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Fields an override reads (to detect crawler corruption) or writes (the corrected text). These are the
# "ranks/fields" compared between seasons to decide whether a season-mismatch warning is actually warranted.
_COMPARED_FIELDS = ("detailed_description", "simple_description", "raw_text")


def _numeric_tokens(text: object) -> list[str]:
    """Ordered numeric tokens in a description line, ignoring formatting noise (a stray '+' prefix, extra
    whitespace, a dash vs a percent sign, etc.) so cosmetic crawler drift doesn't read as a real value change."""
    return _NUM_RE.findall(str(text)) if text else []


def _field_lines(sk: dict, field: str) -> list[str]:
    val = sk.get(field)
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []


def _authored_season_diverges(active_sk: dict, authored_sk: dict | None) -> bool:
    """True if the active season's RAW skill data (pre-override) diverges numerically from the authored-season
    data at any rank/field the override reads or modifies, over the ranks/fields BOTH seasons have data for.
    Fields with no data on one side are skipped (not counted as a divergence) rather than compared.

    Returns True (warn — re-validation needed) when there is nothing overlapping to compare at all: an
    unconfirmed override is treated as "needs re-validation", never silently assumed fine.
    """
    if not authored_sk:
        return True
    compared_anything = False
    for field in _COMPARED_FIELDS:
        active_lines = _field_lines(active_sk, field)
        authored_lines = _field_lines(authored_sk, field)
        for i in range(min(len(active_lines), len(authored_lines))):
            compared_anything = True
            if _numeric_tokens(active_lines[i]) != _numeric_tokens(authored_lines[i]):
                return True
    return not compared_anything


def _load_authored_season_skills(authored_season: str) -> dict[str, dict]:
    from persistence import season_manager
    data = season_manager.load_skills(authored_season) or {}
    return {s["item_id"]: s for s in (data.get("skills") or []) if "item_id" in s}


def apply_skill_overrides(skills_by_id: dict[str, dict], active_season: str) -> list[str]:
    """Patch crawler-mangled skills in place (best effort) and return manual-review warnings."""
    reviews: list[str] = []
    authored_season_cache: dict[str, dict[str, dict]] = {}
    for sid, ov in SKILL_OVERRIDES.items():
        sk = skills_by_id.get(sid)
        if not sk:
            continue
        raw = " ".join(sk.get("detailed_description") or []) + " " + (sk.get("raw_text") or "")
        snippet = ov.get("expects_contains")
        snippet_gone = bool(snippet) and snippet not in raw
        if snippet_gone:
            # The source no longer matches what the override was written to fix — do NOT apply (it could re-break
            # corrected data); surface for manual review.
            reviews.append(f"Skill override '{sid}': source text changed (no longer contains "
                           f"'{snippet}') — override skipped, needs manual review.")
            continue
        authored_season = ov.get("authored_season")
        needs_revalidation = False
        if active_season != authored_season:
            if authored_season not in authored_season_cache:
                authored_season_cache[authored_season] = _load_authored_season_skills(authored_season)
            authored_sk = authored_season_cache[authored_season].get(sid)
            # Compare the RAW (pre-patch) active-season data against the authored season's raw data — if they
            # match at every overlapping rank/field, the override's corrected values are still accurate and the
            # warning would just be crying wolf.
            needs_revalidation = _authored_season_diverges(sk, authored_sk)
        patched = dict(sk)
        for field in ("detailed_description", "simple_description"):
            if ov.get(field) is not None:
                patched[field] = list(ov[field])
        skills_by_id[sid] = patched
        if needs_revalidation:
            reviews.append(f"Skill override '{sid}' was authored for {authored_season} but the active "
                           f"season is {active_season} — re-validate the corrected values against the new data.")
    return reviews
