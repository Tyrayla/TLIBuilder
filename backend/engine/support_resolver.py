"""Resolve attached support skills into engine stat contributions.

This is the GENERAL support→stat path (not Chain-Lightning-specific): given the supports attached to
the main skill, look up each support's full data and emit `{stat_key, amount, text, label}` dicts that
the aggregator injects into the BuildSource (like custom mods), so they ride the existing per-affix
`dmg_additional` pooling in offense.

Scope of THIS pass (Phase 4a): the **"additional damage for the supported skill"** lines only —
  - the **universal** rank line (Noble/Magnificent supports), magnitude from the rank table; and
  - the **specific** tier line(s) from `progression[tier]` (e.g. Web's +16–18%, Merge/Lucky negatives).
Behavioral lines (extra chains / same-target / falloff / "Lucky Damage" / "+N Jump") and the
`(multiplies)` per-Jump line are **deferred to Phase 4b**.

Pooling model — confirmed in-game (docs/CHAIN_LIGHTNING_IMPLEMENTATION_PLAN.md Round 4): **every
support additional line is its own multiplicative ×(1+x) factor; nothing sums.** We achieve that by
giving each emitted line a UNIQUE pooling identity (its `text` is tagged with the support id + role),
so offense's affix_identity keys them distinctly and multiplies them — no change to offense.py.
"""
from __future__ import annotations
import re

# Universal "+% additional damage for the supported skill" by support RANK (1–5). Frame behaviour on
# Noble/Magnificent supports; rank is a per-support build input (not in the game data). Owner-verified.
_RANK_TABLE: dict[int, float] = {1: 0.0, 2: 0.04, 3: 0.08, 4: 0.14, 5: 0.20}

_RANKED_TYPES = {"magnificent_support_skill", "noble_support_skill"}
_UNIVERSAL_PHRASE = "additional damage for the supported skill"
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# Behavioral (non-stat) support effects, parsed from description text (not hardcoded to skill ids).
_FALLOFF_RE = re.compile(r"falloff coefficient of the supported skill is\s*(\d+(?:\.\d+)?)\s*%", re.I)
_RELEASE_CHAINS_RE = re.compile(r"releases?\s+(\d+)\s+additional\s+chain lightning", re.I)
_LUCKY_RE = re.compile(r"deals lucky damage", re.I)


def _range_mid_fraction(value_text: str) -> float | None:
    """Parse a percent range like '+(16–18)' or '(-14.0–-12.0)' → signed mid as a fraction.

    Sign is negative iff the value opens with '(-'/'(−' (the game's format for negative rolls);
    magnitude is the mean of the numbers found. Returns None if no number is present.
    """
    head = value_text.split("%", 1)[0]
    nums = [float(n) for n in _NUM_RE.findall(head)]
    if not nums:
        return None
    mid = sum(nums) / len(nums)
    negative = "(-" in head or "(−" in head
    return (-mid if negative else mid) / 100.0


def _dedup_join(lines: list[str]) -> str:
    """Join description lines, deduping repeated phrases (the raw data repeats some)."""
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines or []:
        s = (ln or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return " ".join(out)


def resolve_support_contributions(
    attached_supports: list[dict] | None,
    skills_by_id: dict[str, dict] | None,
) -> list[dict]:
    """Return a list of {stat_key, amount, text, label} for every attached support's additional-damage
    lines. Empty list when there are no supports or no resolvable lines."""
    if not attached_supports or not skills_by_id:
        return []

    out: list[dict] = []
    for sup in attached_supports:
        item_id = sup.get("item_id")
        data = skills_by_id.get(item_id) if item_id else None
        if not data:
            continue
        skill_type = sup.get("skill_type") or data.get("skill_type") or ""
        name = data.get("name") or item_id

        # 1) Universal rank line — Noble/Magnificent only, and only when the support's data actually
        #    carries the line (summon/minion supports don't; ~12–15% of noble/mag).
        if skill_type in _RANKED_TYPES:
            desc = _dedup_join(data.get("description_lines", [])).lower()
            if _UNIVERSAL_PHRASE in desc:
                rank = _clamp_rank(sup.get("rank"))
                amount = _RANK_TABLE.get(rank, 0.0)
                if amount:  # rank 1 = 0% → contributes nothing; skip
                    out.append({
                        "stat_key": "dmg_additional",
                        "amount": amount,
                        "text": f"{_UNIVERSAL_PHRASE} |{item_id}|universal",
                        "label": f"{name} (Rank {rank})",
                    })

        # 2) Specific tier line(s) from progression[tier] — the support's own roll, NOT rank-scaled.
        tier = _tier_value(sup.get("level"))
        entry = _progression_for_tier(data.get("progression"), tier)
        if entry:
            line = str((entry.get("values") or {}).get("name", ""))
            low = line.lower()
            if "(multiplies)" in low:
                pass  # Augmentation's per-Jump compounding line → Phase 4b
            elif _UNIVERSAL_PHRASE in low:
                frac = _range_mid_fraction(line)
                if frac is not None and frac != 0.0:
                    out.append({
                        "stat_key": "dmg_additional",
                        "amount": frac,
                        "text": f"{_UNIVERSAL_PHRASE} |{item_id}|specific",
                        "label": f"{name} (Tier {tier})",
                    })
    return out


def resolve_support_behavior(
    attached_supports: list[dict] | None,
    skills_by_id: dict[str, dict] | None,
) -> dict:
    """Parse attached supports' description text for behavioral (non-stat) effects that feed offense's
    per-cast hit-list / shotgun. Text-driven, not hardcoded to Chain Lightning's support ids.

    Returns keys (present only when found):
      - same_target_shotgun, falloff_coefficient  ← Merge ("…falloff coefficient … is 80%")
      - chains_per_jump                            ← Web ("…releases 1 additional Chain Lightning")
      - lucky_damage                               ← Lucky ("…deals Lucky Damage")
      - augmentation_per_jump                      ← Augmentation ("…per 1 Jump remaining … (multiplies)")
    Shotgun / Augmentation / Lucky are applied in calculate_offense (shotgun: total-DPS multiplier;
    Augmentation: (1+per)^total_jumps per-hit factor; Lucky: per-type EV scalar on the average).
    """
    behavior: dict = {}
    if not attached_supports or not skills_by_id:
        return behavior
    for sup in attached_supports:
        data = skills_by_id.get(sup.get("item_id"))
        if not data:
            continue
        desc = _dedup_join(data.get("description_lines", []))
        m = _FALLOFF_RE.search(desc)
        if m:
            behavior["same_target_shotgun"] = True
            behavior["falloff_coefficient"] = float(m.group(1)) / 100.0
        m = _RELEASE_CHAINS_RE.search(desc)
        if m:
            behavior["chains_per_jump"] = int(m.group(1))
        if _LUCKY_RE.search(desc):
            behavior["lucky_damage"] = True
        # Augmentation's per-Jump (multiplies) value is tier-specific — read it from progression[tier].
        entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
        if entry:
            line = str((entry.get("values") or {}).get("name", "")).lower()
            if "(multiplies)" in line and "jump" in line:
                frac = _range_mid_fraction(line)
                if frac:
                    behavior["augmentation_per_jump"] = abs(frac)
    return behavior


def _clamp_rank(rank) -> int:
    try:
        r = int(rank)
    except (TypeError, ValueError):
        r = 5
    return max(1, min(5, r))


def _tier_value(level) -> int:
    """The support's tier (the 0–2 'Tier' control). Defaults to 1 (the headline roll)."""
    try:
        return int(level)
    except (TypeError, ValueError):
        return 1


def _progression_for_tier(progression, tier: int) -> dict | None:
    """Find the progression entry whose level == tier; fall back to tier 1, then any entry."""
    if not isinstance(progression, list) or not progression:
        return None
    by_level = {p.get("level"): p for p in progression if isinstance(p, dict)}
    return by_level.get(tier) or by_level.get(1) or progression[0]
