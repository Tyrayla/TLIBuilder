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

from engine.affix_identity import affix_identity

# Empower-effect supports — bespoke (their lines don't map via the generic rules).
_EMP_TEXT_KEYS = ("detailed_description", "simple_description", "raw_text")
_ME_PER_RE = re.compile(r"([\d.]+)\s*%\s*effect for the supported", re.I)   # Mass Effect: per-charge %
_ME_CAP_RE = re.compile(r"up to\s*([\d.]+)\s*%", re.I)
_WFB_PER_RE = re.compile(r"([\d.]+)\s*%\s*effect", re.I)                     # Well-Fought Battle: per-cast %
_WFB_MAX_RE = re.compile(r"stacking up to\s*(\d+)", re.I)

# Support MECHANIC lines (beyond "additional damage for the supported skill"): a SAFE whitelist of stat keys the
# generic resolver may surface from a support's lines via the shared parser (engine.mod_parser). Only these are
# emitted — every other line is left to the additional-damage / bespoke paths so we never misread arbitrary text.
# Emitted SLOT-LOCAL (the supported skill's slot), like the additional-damage lines.
_SUPPORT_MECHANIC_KEYS = frozenset({
    "multistrike_chance", "multistrike_increasing_dmg_inc",
    "multistrike_increasing_dmg_additional", "initial_multistrike_count_flat",
})
# Mechanic stats whose magnitude scales with the support's GEM LEVEL — read the progression[level] value rather
# than the (Lv1) description text. (Multistrike Chance: 101%@L1 → 116%@L16 → 140%@L40.)
_LEVEL_SCALED_MECHANIC_KEYS = frozenset({"multistrike_chance"})


def _support_text(data: dict) -> str:
    parts: list[str] = []
    for k in _EMP_TEXT_KEYS:
        v = data.get(k)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
    return " ".join(parts)


def _empower_support_contrib(item_id, data, sup, conds, source, skills_by_id, slot_skill):
    """Slot-local Empower Skill Effect from Mass Effect (per-charge × host charges, capped) or Well-Fought Battle
    (per-cast × user-set casts, default max). Returns a contrib dict or None. Per-unit value uses the displayed
    (Lv1) value — level-scaling is approximate (flagged)."""
    txt = _support_text(data)
    slot = sup.get("slot", 1)
    name = data.get("name") or item_id
    if item_id == "mass_effect":
        mper = _ME_PER_RE.search(txt)
        if not mper:
            return None
        per = float(mper.group(1)) / 100.0
        cap = (float(_ME_CAP_RE.search(txt).group(1)) / 100.0) if _ME_CAP_RE.search(txt) else per * 3
        from engine.skill_charges import skill_base_charges
        host = skills_by_id.get((slot_skill or {}).get(slot)) or {}
        base_ch = skill_base_charges(host)
        # Charges exist only for cooldown skills; Mass Effect adds +1, plus any +Max Charge mods.
        charges = (base_ch + 1 + int((source.total("max_charge_flat") if source else 0))) if base_ch else 0
        amt = min(per * charges, cap) if charges else 0.0
        if amt <= 0:
            return None
        return {"stat_key": "empower_effect_inc", "amount": amt, "label": name, "slot": slot,
                "text": f"+{amt * 100:.1f}% Empower Skill Effect (Mass Effect, {charges} charges) |mass_effect|me"}
    if item_id == "well_fought_battle":
        wper = _WFB_PER_RE.search(txt)
        if not wper:
            return None
        per = float(wper.group(1)) / 100.0
        maxst = int(_WFB_MAX_RE.search(txt).group(1)) if _WFB_MAX_RE.search(txt) else 3
        raw = (conds or {}).get("well_fought_battle_stacks")
        stacks = maxst if raw is None else max(0, min(int(raw), maxst))
        amt = per * stacks
        if amt <= 0:
            return None
        return {"stat_key": "empower_effect_inc", "amount": amt, "label": name, "slot": slot,
                "text": f"+{amt * 100:.1f}% Empower Skill Effect (Well-Fought Battle, {stacks} casts) |well_fought_battle|wfb"}
    return None


def _explicit_roll(sup: dict, line: str) -> float | None:
    """The user-set roll (signed fraction) for a specific line, keyed by the line's value-stripped
    identity, or None to fall back to the tier midpoint. Mirrors the frontend's identity keying."""
    rolls = sup.get("specific_rolls")
    if isinstance(rolls, dict):
        v = rolls.get(affix_identity(line))
        if v is not None:
            return float(v)
    return None


# Universal "+% additional damage for the supported skill" by support RANK (1–5). Frame behaviour on
# Noble/Magnificent supports; rank is a per-support build input (not in the game data). Tyra-verified.
_RANK_TABLE: dict[int, float] = {1: 0.0, 2: 0.04, 3: 0.08, 4: 0.14, 5: 0.20}

_RANKED_TYPES = {"magnificent_support_skill", "noble_support_skill"}
_UNIVERSAL_PHRASE = "additional damage for the supported skill"
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# A crawler artifact: a progression `name` sometimes glues a "stacking up to N time(s)" clause directly onto
# a following "When/While/If …" gated sentence with no separating punctuation (~50 lines season-wide, e.g.
# Crossed Lightning's Chain Lightning Quantity clause run into its Dexterity-threshold damage clause). Split
# on that exact boundary before any per-line condition parsing (see the specific-tier-line loop below).
_RUNON_SENTENCE_RE = re.compile(r"(?<=\btime\(s\))\s+(?=(?:when|while|if)\b)", re.I)

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


def _norm_line(s: str) -> str:
    return re.sub(r"[\s%]+", "", s or "").lower()


def _progression_value_for_line(prog_entry: dict, line: str) -> float | None:
    """The level-scaled numeric for `line` from a progression entry's `values` (keyed by the Lv1 line text).
    Falls back to the single value when the entry has exactly one (e.g. Multistrike's chance-only progression)."""
    vals = (prog_entry or {}).get("values") or {}
    nl = _norm_line(line)
    for k, v in vals.items():
        if _norm_line(k) == nl:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    if len(vals) == 1:
        try:
            return float(next(iter(vals.values())))
        except (TypeError, ValueError):
            return None
    return None


def _support_mechanic_contribs(sup: dict, data: dict) -> list[dict]:
    """Slot-local MECHANIC contributions (Multistrike chance / increment / initial count, …) parsed from a
    support's lines — whitelisted stats only, with gem-level scaling for the ones that scale. Generic: any
    support carrying these lines flows through here (the Multistrike support, Wind Stalker's granted support,
    future sources), so we don't write a bespoke resolver per support."""
    from engine.mod_parser import _parse_custom_mod_text
    name = data.get("name") or sup.get("item_id")
    slot = sup.get("slot", 1)
    prog_entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    seen: set = set()
    out: list[dict] = []
    for line in (data.get("description_lines") or []):
        # "for every / for each X" lines are CONDITIONAL scaling (e.g. "+12% increment for every 1 Sentry",
        # "+1 Projectile for every 80% Multistrike chance") — not flat grants. The generic parser would grab the
        # number and drop the qualifier, so skip them here (they need bespoke per-skill handling when modeled).
        if re.search(r"\bfor\s+(?:every|each)\b", line, re.I):
            continue
        for parsed in (_parse_custom_mod_text(line) or []):
            sk = parsed.get("stat_key")
            if sk not in _SUPPORT_MECHANIC_KEYS or sk in seen:
                continue
            amount = parsed.get("amount", 0.0)
            if sk in _LEVEL_SCALED_MECHANIC_KEYS:
                scaled = _progression_value_for_line(prog_entry, line)
                if scaled is not None:
                    amount = scaled / 100.0
            if amount == 0.0:
                continue
            seen.add(sk)
            out.append({"stat_key": sk, "amount": amount,
                        "text": f"{line.strip()} |{sup.get('item_id')}|mechanic",
                        "label": name, "source_name": name, "slot": slot})
    return out


def resolve_support_contributions(
    attached_supports: list[dict] | None,
    skills_by_id: dict[str, dict] | None,
    translate_cond=None,
) -> list[dict]:
    """Return a list of {stat_key, amount, text, label[, condition]} for every attached support's
    additional-damage lines. Empty list when there are no supports or no resolvable lines.

    `translate_cond` (server._translate_condition_expr, injected like the node resolver) gates a SPECIFIC
    tier line that carries a condition ("…when only 1 enemy nearby"): the condition is split off and
    translated; an untranslatable gate drops the line rather than applying it always-on (the old bug)."""
    from engine.core_talent_resolver import _split_condition
    # Lazy import (skill_effects modules import helpers from this module → avoid a circular import at load).
    from engine import skill_effects
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

        # 0) Mechanic lines (Multistrike chance/increment, …) — whitelisted, slot-local, level-scaled. Runs for
        #    every support; emits nothing unless a whitelisted phrase is present.
        out.extend(_support_mechanic_contribs(sup, data))

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
                        "source_name": name,
                        "slot": sup.get("slot", 1),
                    })

        # Bespoke/deferred canvas supports + activation mediums (per engine.skill_effects): their SPECIFIC line is
        # handled elsewhere — a skill module's type-A contribution, or (activation mediums) the AM roll parser +
        # slot-level wiring hook. Skip the generic parser (it would misread / double-count these). Universal +20%
        # above still applies where relevant.
        if skill_effects.is_guarded(item_id):
            c = skill_effects.support_contribution(sup, data)
            if c:
                c.setdefault("source_name", name)
                out.append(c)
            continue

        # 2) Specific tier line(s) from progression[tier] — the support's own roll, NOT rank-scaled. Noble/Mag
        #    ONLY: a STANDARD support's damage lines are resolved by engine.support_resolver.resolve_standard_supports
        #    (parser + mapper) in the compute loop, so parsing them here too double-counts them (e.g. Critical Strike
        #    Damage Increase landed as BOTH dmg_additional_on_crit here AND dmg_additional there).
        if skill_type not in _RANKED_TYPES:
            continue
        tier = _tier_value(sup.get("level"))
        entry = _progression_for_tier(data.get("progression"), tier)
        if entry:
            full_line = str((entry.get("values") or {}).get("name", ""))
            # "+X% additional damage for the supported skill when it lands a Critical Strike" (Critical Strike
            # Damage Increase) → the crit-weighted additional-damage pool (offense scales it by the finalized crit
            # chance), NOT a plain always-on additional. Its progression is keyed by the LINE TEXT (no "name"
            # key), so detect it among the values keys + read the level-scaled value. Handled before the generic
            # condition-split (which would drop the untranslatable crit gate). Matches Razor Leaf's crit weighting.
            _crit_key = next((k for k in ((entry.get("values") or {}))
                              if _UNIVERSAL_PHRASE in k.lower() and re.search(r"lands?\s+a\s+critical\s+strike", k, re.I)),
                             None)
            if _crit_key:
                v = _progression_value_for_line(entry, _crit_key)
                if v:
                    out.append({
                        "stat_key": "dmg_additional_on_crit", "amount": v / 100.0,
                        "text": f"{_UNIVERSAL_PHRASE} on Critical Strike |{item_id}|specific",
                        "label": f"{name} (Tier {tier})", "source_name": name, "slot": sup.get("slot", 1),
                    })
                continue
            # A progression `name` sometimes GLUES two independent sentences with no separating punctuation
            # (~50 occurrences season-wide, e.g. Crossed Lightning: "...stacking up to 6 time(s) When having at
            # least 240 Dexterity, +42% additional damage..."). Split on that glue point FIRST, so a following
            # sentence's own untranslatable gate can't swallow (and zero out) an unrelated preceding clause's
            # stat text — each sentence is condition-split and resolved independently below.
            for line in _RUNON_SENTENCE_RE.split(full_line) if full_line else [full_line]:
                if not line:
                    continue
                # Split off & translate a condition ("…when only 1 enemy nearby") so the line is GATED, not
                # applied always-on. Untranslatable gate → drop the line (don't inflate DPS ungated).
                stat_clause, cond_part = _split_condition(line)
                cond_expr = None
                if cond_part is not None and translate_cond is not None:
                    cond_expr = translate_cond(line) or translate_cond(cond_part)
                    if cond_expr is None:
                        stat_clause = ""
                low = stat_clause.lower()
                if "(multiplies)" in low:
                    pass  # Augmentation's per-Jump compounding line → resolve_support_behavior
                elif "additional hit damage for the supported skill" in low:
                    # Generic "+X% additional Hit Damage for the supported skill" → the hit-only additional pool.
                    # (The universal phrase below only matches "additional DAMAGE…"; this is the "…HIT DAMAGE…" variant.)
                    roll = _explicit_roll(sup, line)
                    frac = roll if roll is not None else _range_mid_fraction(stat_clause)
                    if frac is not None and frac != 0.0:
                        out.append({
                            "stat_key": "hit_dmg_additional",
                            "amount": frac,
                            "text": "additional Hit Damage for the supported skill |{}|specific".format(item_id),
                            "label": f"{name} (Tier {tier})",
                            "source_name": name,
                            "condition": cond_expr,
                            "slot": sup.get("slot", 1),
                        })
                elif _UNIVERSAL_PHRASE in low:
                    roll = _explicit_roll(sup, line)
                    frac = roll if roll is not None else _range_mid_fraction(stat_clause)
                    if frac is not None and frac != 0.0:
                        out.append({
                            "stat_key": "dmg_additional",
                            "amount": frac,
                            "text": f"{_UNIVERSAL_PHRASE} |{item_id}|specific",
                            "label": f"{name} (Tier {tier})",
                            "source_name": name,
                            "condition": cond_expr,
                            "slot": sup.get("slot", 1),
                        })
    return out


def resolve_support_behavior(
    attached_supports: list[dict] | None,
    skills_by_id: dict[str, dict] | None,
) -> dict:
    """Parse attached supports' description text for behavioral (non-stat) effects that feed offense's
    per-cast hit-list / shotgun. Text-driven, not hardcoded to Chain Lightning's support ids.

    Returns a PER-SLOT map `{slot: {behavior keys}}` (a support belongs to its host skill's slot, default
    1) so each slot's offense pass reads only its own supports' behavior. Per-slot keys (present only when
    found):
      - same_target_shotgun, falloff_coefficient  ← Merge ("…falloff coefficient … is 80%")
      - chains_per_jump                            ← Web ("…releases 1 additional Chain Lightning")
      - lucky_damage                               ← Lucky ("…deals Lucky Damage")
      - augmentation_per_jump                      ← Augmentation ("…per 1 Jump remaining … (multiplies)")
    Shotgun / Augmentation / Lucky are applied in calculate_offense (shotgun: total-DPS multiplier;
    Augmentation: (1+per)^total_jumps per-hit factor; Lucky: per-type EV scalar on the average).
    """
    by_slot: dict[int, dict] = {}
    if not attached_supports or not skills_by_id:
        return by_slot
    for sup in attached_supports:
        data = skills_by_id.get(sup.get("item_id"))
        if not data:
            continue
        behavior = by_slot.setdefault(sup.get("slot", 1), {})
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
                roll = _explicit_roll(sup, line)
                frac = roll if roll is not None else _range_mid_fraction(line)
                if frac:
                    behavior["augmentation_per_jump"] = abs(frac)
    return by_slot


def _clamp_rank(rank) -> int:
    # Default to rank 1 (= 0% universal) when unset — the conservative/accurate default; the user
    # raises it to match their actual support.
    try:
        r = int(rank)
    except (TypeError, ValueError):
        r = 1
    return max(1, min(5, r))


def _tier_value(level) -> int:
    """The support's tier (the 0–2 'Tier' control). Defaults to 1 (the headline roll)."""
    try:
        return int(level)
    except (TypeError, ValueError):
        return 1


# Skill-type/element tags a support can carry → the per-type skill-level stat it gains from.
_SUPPORT_LEVEL_TAGS = ("attack", "spell", "melee", "projectile", "ranged", "channeled",
                       "fire", "cold", "lightning", "erosion", "physical")


def _support_level_bonus(source, tags) -> int:
    """Extra effective levels a support gains from skill-level sources: global (all/support skill level) plus
    any matching its OWN tags (e.g. Quick Return has the Attack tag → gains +Attack Skill Level; Off the Beaten
    Track grants +4 Support Skill Level). Rounded down. `source` None → 0 (used by tooltip/badge paths)."""
    if source is None:
        return 0
    bonus = source.total("all_skill_level") + source.total("support_skill_level")
    tl = {t.lower() for t in (tags or [])}
    for t in _SUPPORT_LEVEL_TAGS:
        if t in tl:
            bonus += source.total(f"{t}_skill_level")
    return int(bonus)


def _progression_for_tier(progression, tier: int) -> dict | None:
    """Find the progression entry whose level == tier; fall back to tier 1, then any entry."""
    if not isinstance(progression, list) or not progression:
        return None
    by_level = {p.get("level"): p for p in progression if isinstance(p, dict)}
    return by_level.get(tier) or by_level.get(1) or progression[0]


# ── Standard supports (support_skill / activation_medium) via the description_lines mapper ──────
_STANDARD_TYPES = {"support_skill", "activation_medium_skill"}

# Willpower's per-stack additional-damage % is LEVEL-specific and lives in the per-level Descript (not
# the rolled values): Lv1 4.1% / Lv16 5.6% / Lv20 6% — verified in-game (L16 = 1.056^6). Read it here.
_WILLPOWER_RE = re.compile(r"([\d.]+)\s*%\s*additional damage for the supported skill for every stack of buffs", re.I)


def _willpower_per_stack(data: dict, level: int) -> float | None:
    entry = _progression_for_tier(data.get("progression"), level)
    m = _WILLPOWER_RE.search((entry or {}).get("values", {}).get("Descript", "")) if entry else None
    return float(m.group(1)) / 100.0 if m else None


def resolve_standard_supports(attached_supports, skills_by_id, main_cat, main_dtypes, conds, slot_cats=None,
                              source=None, curse_slots=None, empower_slots=None, slot_skill=None):
    """Resolve standard supports via the parser + mapper (engine.support_lines / support_mapper).
    Returns (stat_contributions, condition_effects). Run INSIDE the fixed-point loop so conditional
    lines see converging conditions and auto-derived conditions feed back. Noble/Magnificent stay in
    resolve_support_contributions.

      main_cat    'spell' | 'attack' | None — fallback category when a support's slot isn't in slot_cats
      main_dtypes the supported skill's damage types (for 'inflicts X when deals Y' gates)
      conds       the current condition_state ({key: value|bool})
      slot_cats   {slot: 'spell'|'attack'|None} — each support resolves against ITS host skill's category
                  (tag-gate + added-flat), so a non-main-slot skill's supports route to the right pool
    """
    from engine.support_lines import parse_support
    from engine.support_mapper import map_line, map_autoderive_line

    contribs: list[dict] = []
    effects: list = []
    if not attached_supports or not skills_by_id:
        return contribs, effects

    for sup in attached_supports:
        item_id = sup.get("item_id")
        data = skills_by_id.get(item_id) if item_id else None
        if not data:
            continue
        stype = sup.get("skill_type") or data.get("skill_type") or ""
        if stype not in _STANDARD_TYPES:
            continue  # Noble/Magnificent handled elsewhere
        # Gate + categorize against THIS support's host skill (its slot), not the main skill.
        cat = (slot_cats or {}).get(sup.get("slot", 1), main_cat)
        parsed = parse_support(data)
        if (parsed.gate == "spell-only" and cat != "spell") or \
           (parsed.gate == "attack-only" and cat != "attack") or \
           (parsed.gate == "curse-only" and sup.get("slot", 1) not in (curse_slots or set())) or \
           (parsed.gate == "empower-only" and sup.get("slot", 1) not in (empower_slots or set())):
            continue  # Attack/Spell/Curse/Empower tag-gate
        level = _tier_value(sup.get("level")) + _support_level_bonus(source, data.get("skill_tags"))
        name = data.get("name") or item_id

        # Empower-effect supports (bespoke): contribute slot-local Empower Skill Effect scaled by the host skill's
        # charges (Mass Effect) or a user-set cast count (Well-Fought Battle, default max). Their lines don't map
        # via the generic rules, so handle here. Level-scaling of the per-unit value is approximate (uses the
        # displayed/Lv1 value) — flagged for later.
        if item_id in ("mass_effect", "well_fought_battle"):
            c = _empower_support_contrib(item_id, data, sup, conds, source, skills_by_id, slot_skill)
            if c:
                contribs.append(c)
            continue

        for line in parsed.lines:
            for c in map_line(line, level, cat, conds):
                contribs.append({
                    "stat_key": c.stat_key,
                    "amount": c.amount,
                    # unique pooling identity per support line (multiplies, like Noble/Mag)
                    "text": f"{c.text} |{item_id}|{line.template[:24]}",
                    "label": name,
                    "slot": sup.get("slot", 1),
                })
            effects.extend(map_autoderive_line(line))

        # Willpower: compounding per-stack buff whose % is per-level (Descript), applied while standing
        # still. Resolved here (not in the aggregator) so it uses the support's actual level value.
        wp = _willpower_per_stack(data, level)
        if wp is not None and (conds or {}).get("standing_still"):
            stacks = float((conds or {}).get("willpower_stacks", 0) or 0)
            if stacks > 0:
                contribs.append({
                    "stat_key": "dmg_additional",
                    "amount": (1.0 + wp) ** stacks - 1.0,
                    "text": f"+{wp * 100:.1f}% additional damage per Willpower stack (multiplies) |{item_id}|wp",
                    "label": name,
                    "slot": sup.get("slot", 1),
                })
    return contribs, effects
