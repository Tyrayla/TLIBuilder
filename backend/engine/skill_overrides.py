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
  - if the active season differs from authored_season → still apply (best effort) but flag for manual re-validation.
"""
from __future__ import annotations

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


def apply_skill_overrides(skills_by_id: dict[str, dict], active_season: str) -> list[str]:
    """Patch crawler-mangled skills in place (best effort) and return manual-review warnings."""
    reviews: list[str] = []
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
        patched = dict(sk)
        for field in ("detailed_description", "simple_description"):
            if ov.get(field) is not None:
                patched[field] = list(ov[field])
        skills_by_id[sid] = patched
        if active_season != ov.get("authored_season"):
            reviews.append(f"Skill override '{sid}' was authored for {ov.get('authored_season')} but the active "
                           f"season is {active_season} — re-validate the corrected values against the new data.")
    return reviews
