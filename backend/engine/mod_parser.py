"""Authoritative freeform modifier-text → engine stat-key parser.

This is the SINGLE source of truth for "modifier phrase → (stat_key, pool, type, scope)". It lives in the engine
layer so BOTH the server (gear / spirit / memory / talent / custom resolution) and the engine's own
support_mapper can call it — eliminating the parallel `_DMG_RULES`/`_CAPTURE_RULES` tables that used to drift
(e.g. "additional Skill Area" landing in the increased pool on supports but the additional pool on gear).

Increased-vs-additional pooling and the damage type are decided by stat_meta (via `_get_gear_candidates`), never
by ad-hoc per-call tables. Depends only on stat_meta + engine.skill_scope — no FastAPI / server state.
"""
from __future__ import annotations
import re

from engine.skill_scope import detect_skill_scope

# ── Gear/affix text normalization tables ─────────────────────────────────────
_GEAR_STOP_WORDS = {"of", "the", "a", "an", "to", "by", "from", "with", "and", "or", "in", "on", "per", "second", "dealt"}
_GEAR_NORMALIZE_MAP = {
    "regenerates": "regeneration",
    "regenerate":  "regeneration",
    "reduces":     "reduction",
    "reduce":      "reduction",
    "splits":      "split",
}
_GEAR_COND_RE = re.compile(
    r"\s+(?:while\b|when\b|if\b|against\b|recently\b|on\s+hit\b|upon\b|"
    r"for\s+every\b|for\s+each\b)",
    re.I,
)
# Trailing "for/to this gear" / "to the gear" qualifier (gear-local affix), stripped before normalization.
_GEAR_SUFFIX_RE = re.compile(r"\s+(?:(?:for|to)\s+this\s+gear|to\s+the\s+gear)\s*$", re.I)

# Exact normalized-expression → stat overrides (wording that the fuzzy display-name match would miss or mis-tie).
_EXPRESSION_STAT_OVERRIDES: dict[str, str] = {
    # Hero-memory alias: in-game wording "for Combo Finishers" isn't a skill-type scope, so it stays in the
    # phrase; map it to the combo-finisher crit-damage stat (ported from the old _MEMORY_ALIAS_LOOKUP).
    "+(#) % critical strike damage for combo finishers": "combo_finisher_crit_dmg_inc",
    # Abbreviated penetration wording used by spirit/memory effects ("Fire Penetration" vs gear's "Fire
    # Resistance Penetration"). Pin to the PLAYER pen stat — without this, fuzzy matching ties "Fire
    # Penetration" with "Minion Fire Penetration" and mis-resolves to the minion variant.
    "+(#) % fire penetration":      "fire_pen",
    "+(#) % cold penetration":      "cold_pen",
    "+(#) % lightning penetration": "lightning_pen",
    "+(#) % erosion penetration":   "erosion_pen",
    "+(#) % elemental penetration": "elemental_pen",
    # Flat-count core-talent lines whose in-game wording differs from the stat's gear display name
    # (reached value-stripped via the trailing-count handler in _parse_custom_mod_text).
    "max sentry quantity":  "max_sentry_quantity_flat",
    "min channeled stacks": "min_channeled_stacks_flat",
    "+(#) gear armor":   "armor_gear_flat",
    "+(#) % gear armor": "armor_gear_inc",
    "+(#) gear evasion":   "evasion_gear_flat",
    "+(#) % gear evasion": "evasion_gear_inc",
    # Damage conversion — physical
    "adds (#) % of physical damage as lightning damage": "physical_as_lightning",
    "adds (#) % of physical damage to cold damage":      "physical_as_cold",
    "adds (#) % of physical damage as cold damage":      "physical_as_cold",
    # Channeled-scoped speed (after the "Attack and Cast Speed" shared-stat split)
    "+(#) % attack speed for channeled skills": "channeled_attack_speed_inc",
    "+(#) % cast speed for channeled skills":   "channeled_cast_speed_inc",
    "adds (#) % of physical damage as fire damage":      "physical_as_fire",
    "adds (#) % of physical damage as erosion damage":   "physical_as_erosion",
    # Damage conversion — elemental to erosion
    "adds (#) % of lightning damage as erosion damage":  "lightning_as_erosion",
    "adds (#) % of cold damage as erosion damage":       "cold_as_erosion",
    "adds (#) % of fire damage as erosion damage":       "fire_as_erosion",
    # Damage conversion — adds-as gaps (up-chain: lightning→cold/fire, cold→fire)
    "adds (#) % of lightning damage as cold damage":     "lightning_as_cold",
    "adds (#) % of lightning damage as fire damage":     "lightning_as_fire",
    "adds (#) % of cold damage as fire damage":          "cold_as_fire",
    # Damage conversion — convert (reduces source). "converts (#)% of A damage to B damage".
    "converts (#) % of physical damage to lightning damage": "physical_convert_to_lightning",
    "converts (#) % of physical damage to cold damage":      "physical_convert_to_cold",
    "converts (#) % of physical damage to fire damage":      "physical_convert_to_fire",
    "converts (#) % of physical damage to erosion damage":   "physical_convert_to_erosion",
    "converts (#) % of lightning damage to cold damage":     "lightning_convert_to_cold",
    "converts (#) % of lightning damage to fire damage":     "lightning_convert_to_fire",
    "converts (#) % of lightning damage to erosion damage":  "lightning_convert_to_erosion",
    "converts (#) % of cold damage to fire damage":          "cold_convert_to_fire",
    "converts (#) % of cold damage to erosion damage":       "cold_convert_to_erosion",
    "converts (#) % of fire damage to erosion damage":       "fire_convert_to_erosion",
    # Damage taken conversion
    "converts (#) % of physical damage taken to lightning damage": "physical_taken_as_lightning_inc",
    "converts (#) % of physical damage taken to cold damage":      "physical_taken_as_cold_inc",
    "converts (#) % of physical damage taken to fire damage":      "physical_taken_as_fire_inc",
    "converts (#) % of erosion damage taken to lightning damage":  "erosion_taken_as_lightning_inc",
    "converts (#) % of erosion damage taken to cold damage":       "erosion_taken_as_cold_inc",
    "converts (#) % of erosion damage taken to fire damage":       "erosion_taken_as_fire_inc",
    # Mana/life
    "(#) % of damage is taken from mana before life":    "mana_before_life_inc",
    # Attack / ranged
    "+(#) % ranged damage":                              "ranged_dmg_inc",
    # Skill levels
    "+(#) main skill level":                             "main_skill_level",
    # Channeled
    "min channeled stacks +(#)":                         "min_channeled_stacks_flat",
    # Terra
    "max terra charge stacks +(#)":                      "max_terra_charge_stacks_flat",
    "+(#) % terra charge recovery speed":                "terra_charge_recovery_speed_inc",
    "max terra quantity +(#)":                           "max_terra_quantity_flat",
    # Warcry
    "+(#) max warcry skill charges":                     "max_warcry_skill_charges_flat",
    # Shadow
    "shadow quantity +(#)":                              "max_shadow_quantity_flat",
    # Ignite
    "+(#) ignite limit":                                 "max_ignite_flat",
    # Ailment durations
    "+(#) % ailment duration":                           "ailment_duration_inc",
    "+(#) % ignite duration":                            "ignite_duration_inc",
    # Spirit magi
    "+(#) initial growth for spirit magi":               "spirit_magi_initial_growth_flat",
    # Elixir
    "elixir skills gain (#) charging progress every second":    "elixir_charging_progress_flat",
    "elixir skills gain (#) of charging progress every second": "elixir_charging_progress_flat",
    # Minion
    "minion damage penetrates (#) % elemental resistance": "minion_elemental_pen",
    "+(#) % minion elemental damage":                    "minion_elemental_dmg_inc",
    # Hit/taunt — "on hit" is stripped by _GEAR_COND_RE before dict lookup
    "+(#) % chance for attacks to inflict taunt on enemies": "attack_taunt_on_hit_chance",
    "+(#) % chance for attacks to taunt":                   "attack_taunt_on_hit_chance",
    # Curse
    "-(#)-(#) % curse effect against you":               "curse_effect_against_inc",
    # Damage to life
    "(#) % additional damage applied to life":           "dmg_to_life_additional",
    # Defense additional
    "+(#) % additional armor":                           "armor_additional",
    "+(#) % additional evasion":                         "evasion_additional",
    "+(#) % additional max life":                        "max_life_additional",
    "+(#) % additional armor while moving":              "armor_additional",
    "+(#) % armor effective rate for non-physical damage": "armor_effective_rate_non_physical_inc",
    # Ailment additional
    "+(#) % additional trauma damage":                   "trauma_dmg_additional",
    "+(#) % additional wilt damage":                     "wilt_dmg_additional",
    "+(#) % additional ignite damage":                   "ignite_dmg_additional",
    # Affliction
    "+(#) affliction inflicted per second":              "affliction_per_second_flat",
    # Sentry
    "max sentry quantity +(#)":                          "max_sentry_quantity_flat",
    # Barrage
    "barrage skills +(#) % damage increase per wave":    "barrage_dmg_per_wave_inc",
    # Warcry (text variant with prefix "Warcry is cast immediately")
    "warcry is cast immediately +(#) max warcry skill charges": "max_warcry_skill_charges_flat",
    # Defense
    "+(#) % additional defense gained from shield":      "shield_defense_additional",
    # Tangle. Enhancement is its OWN additive-within-itself multiplier (NOT the increased pool); additional
    # Tangle Damage is the multiplicative additional pool; crit rating is flat; attach range is display-only.
    "+(#) % tangle damage enhancement":                  "tangle_dmg_enhancement_additional",
    "+(#) % additional tangle damage":                   "tangle_dmg_additional",
    "+(#) tangle critical strike rating":                "tangle_crit_rating_flat",
    "+(#) % tangle attach range":                        "tangle_attach_range_inc",
    # Shadow damage
    "+(#) % additional shadow damage":                   "shadow_dmg_additional",
    # Spell burst hit damage (single value)
    "+(#) % additional hit damage for skills cast by spell burst": "spell_burst_hit_dmg_additional",
    # Critical Strike Rating — gear-specific % (scales gear flat only) and main-hand weapon
    "+(#) % attack critical strike rating for this gear":          "attack_crit_rating_gear",
    "+(#) % critical strike rating for the main-hand weapon":      "attack_crit_rating_mh",
    "+(#) % additional damage for the main-hand weapon":           "main_hand_dmg_additional",
    # Flat defense — "maximum X" fuzzy-matches the derived stat key; override to the raw flat input stat
    "+(#) maximum life":             "max_life_flat",
    "+(#) to maximum life":          "max_life_flat",
    "+(#) maximum mana":             "max_mana_flat",
    "+(#) to maximum mana":          "max_mana_flat",
    "+(#) maximum energy shield":    "energy_shield_gear_flat",
    "+(#) to maximum energy shield": "energy_shield_gear_flat",
}

# Words that appear in both singular and plural forms in raw affix text.
# All override dict keys use the singular canonical form.
_EXPR_WORD_CANON: dict[str, str] = {
    "splits":    "split",
    "tangle(s)": "tangle",
    "stack(s)":  "stack",
}

# Pool qualifier → modifier_type (pool-strict matching). "reduced" shares the increased pool (negative value).
_POOL_QUALIFIERS = {"additional": "additional", "increased": "increased", "reduced": "increased"}
_POOL_QUALIFIER_WORDS = frozenset(_POOL_QUALIFIERS)

# Custom mod text parsing — freeform modifier text → stat contributions
_CUSTOM_RANGE_RE  = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s+(.*)', re.IGNORECASE)
_CUSTOM_SINGLE_RE = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\s*(%?)\s+(.*)', re.IGNORECASE)
# "Adds N-N <Type> Damage to <Attacks|Spells|Attacks and Spells>" → flat <type>_<dest>_dmg_flat_min/max.
_CUSTOM_ADDS_RE = re.compile(
    r'^\s*adds\s+([\d.]+)\s*[-–]\s*([\d.]+)\s+(physical|fire|cold|lightning|erosion)\s+damage\s+to\s+'
    r'(attacks and spells|attacks|spells)\b', re.IGNORECASE)
# Modifier verbs that appear in game text but not in stat display names — strip before fuzzy match
_CUSTOM_VERB_RE   = re.compile(r'\b(increased|reduced|more|less)\b', re.IGNORECASE)

# Lazily-built gear-candidate list (stat_val, display_name, display_words, unit, modifier_type) from stat_meta.
_gear_candidates = None


def _gear_normalize(text: str) -> set[str]:
    text = _GEAR_SUFFIX_RE.sub("", text)
    clean = re.sub(r"[^a-z\s]", " ", text.lower())
    return {_GEAR_NORMALIZE_MAP.get(w, w) for w in clean.split()
            if w not in _GEAR_STOP_WORDS and not re.fullmatch(r"\d+", w)}


def _get_gear_candidates() -> list:
    global _gear_candidates
    if _gear_candidates is None:
        from models.stat_meta import STAT_META
        _gear_candidates = []
        for stat, meta in STAT_META.items():
            # Derived stats (Strength/Armor/Max Life totals, …) are computed OUTPUTS, never a resolution
            # target — excluding them means "+N Strength" can only ever resolve to strength_flat, removing
            # the display-name collision with the derived stat at the source (not just via a tie-break).
            if meta.modifier_type == "derived":
                continue
            # Drop pool-qualifier words from the candidate's display words too, so a name like
            # "Additional Minion Damage" matches on {minion, damage} and the pool is decided solely by
            # modifier_type (kept separately) — never by the word "additional" appearing in the name.
            words = _gear_normalize(meta.display_name) - _POOL_QUALIFIER_WORDS
            if words:
                _gear_candidates.append((stat.value, meta.display_name, words, meta.unit, meta.modifier_type))
    return _gear_candidates


def _norm_expr(text: str) -> str:
    """Normalize an affix expression for dict lookup."""
    # Normalize unicode dashes (en dash U+2013, em dash U+2014) to regular hyphen first
    s = text.replace("–", "-").replace("—", "-")
    s = s.replace(",", " ")  # remove commas (e.g., "Life, Mana, and Energy Shield")
    s = re.sub(r"\d+(?:\.\d+)?", "#", s.lower()).strip()
    s = re.sub(r"\(#-#\)", "(#)", s)        # collapse ranged value "(#-#)" → "(#)"
    s = re.sub(r"(?<!\()#(?!\))", "(#)", s) # wrap bare # not already in parens → "(#)"
    s = re.sub(r"\s*%\s*", " % ", s)        # normalize spaces around %
    s = re.sub(r"\s+-\s+", "-", s)          # collapse spaced dashes: "(#) - (#)" → "(#)-(#)"
    s = re.sub(r"\s+", " ", s).strip()
    # normalize plural/singular word variants
    words = s.split(" ")
    s = " ".join(_EXPR_WORD_CANON.get(w, w) for w in words)
    return s


def _normalize_for_custom_resolve(text: str) -> str:
    """Strip gaming modifier verbs so the fuzzy matcher aligns with stat display names."""
    return re.sub(r'\s+', ' ', _CUSTOM_VERB_RE.sub('', text)).strip()


def _resolve_gear_stat(raw_text: str) -> tuple[str | None, str]:
    """Return (stat_key, unit) for a gear affix, or (None, '') if unresolved.

    Pool-strict: an "additional" modifier only matches an `additional` stat, and
    "increased"/"reduced" only an `increased` stat. If the text carries a pool qualifier but no
    same-pool stat matches, the affix is left UNRESOLVED rather than silently placed in the wrong pool.
    """
    text = _GEAR_COND_RE.sub("", raw_text)
    norm_expr = _norm_expr(text)
    if norm_expr in _EXPRESSION_STAT_OVERRIDES:
        stat_key = _EXPRESSION_STAT_OVERRIDES[norm_expr]
        unit = "%" if "%" in raw_text else ""
        return stat_key, unit
    query = _gear_normalize(text)
    if not query:
        return None, ""
    # Detect the pool qualifier, then drop it from the query so it neither pollutes the word overlap
    # nor is required to appear in the (qualifier-free) display name.
    want_pool = next((_POOL_QUALIFIERS[w] for w in query if w in _POOL_QUALIFIERS), None)
    query = {w for w in query if w not in _POOL_QUALIFIERS}
    if not query:
        return None, ""
    is_pct = "%" in raw_text
    scores = []
    for stat_val, dn, dn_words, unit, mtype in _get_gear_candidates():
        if want_pool is not None and mtype != want_pool:
            continue   # pool-strict: never cross "additional" with "increased"
        overlap = len(query & dn_words)
        if not overlap:
            continue
        scores.append((overlap / len(query | dn_words), stat_val, dn, unit))
    if not scores:
        return None, ""
    scores.sort(key=lambda x: x[0], reverse=True)
    best_score, best_stat, best_dn, best_unit = scores[0]
    extra = query - _gear_normalize(best_dn)
    if best_score < (0.7 if extra else 0.5):
        return None, ""
    tied = [s for s in scores if s[0] == best_score]
    if len(tied) == 1:
        return best_stat, best_unit
    # Break ties within the matched pool (additional → _additional; else _inc for %, _flat otherwise).
    suffix = "_additional" if want_pool == "additional" else ("_inc" if is_pct else "_flat")
    pref = [s for s in tied if s[1].endswith(suffix)]
    return (pref[0][1], pref[0][3]) if len(pref) == 1 else (None, "")


def _parse_custom_mod_text(text: str) -> list[dict]:
    """Resolve freeform modifier text to {stat_key, amount, text, scope?} dicts. Thin wrapper that peels a
    skill-type scope qualifier ('… for Attack Skills') off first (shared engine.skill_scope helper),
    resolves the RESIDUAL via the unchanged base resolver, then tags the results with the scope and restores
    the ORIGINAL full text (incl. scope words) so the additional pool's affix-identity keeps scoped mods as
    distinct multiplicative factors."""
    residual, scope = detect_skill_scope(text.strip())
    results = _parse_custom_mod_text_base(residual)
    if not results:
        # Fallback: an INLINE skill-type qualifier the suffix detector + base resolver miss ("Melee Skill
        # Damage", "Melee Attack Speed"). Peel it and retry; only adopt the scope if the residual resolves,
        # so working typed-stat phrasings (resolved on the first try above) are never disturbed.
        from engine.skill_scope import detect_inline_skill_scope
        inline_residual, inline_scope = detect_inline_skill_scope(residual)
        if inline_scope and inline_residual != residual:
            retry = _parse_custom_mod_text_base(inline_residual)
            if retry:
                results, scope = retry, inline_scope
    if scope and results:
        original = text.strip()
        for d in results:
            d["scope"] = scope
            d["text"] = original
    return results


def _parse_custom_mod_text_base(text: str) -> list[dict]:
    """Resolve freeform modifier text to a list of {stat_key, amount, text} dicts.

    Routes through the existing gear stat resolver so all supported modifier text
    forms work, including percentage-based mods, flat adds, and ranges.
    Returns an empty list if the text cannot be resolved.

    Scale is determined by whether the user explicitly typed '%' — not by the stat's
    metadata unit — so that raw flat stats (CSR, flat damage) are not accidentally
    divided by 100.
    """
    t = text.strip()

    # Collapse a LEADING paren value-range to its midpoint so range-template text resolves like a single
    # value: "+(20-25) % X" → "+22.5 % X", "+(44–54) % Elemental Damage" → "+49 % …". Start-anchored, so it
    # never touches "Adds (A-B) - (C-D)" gear-flat lines (those start with "Adds", handled elsewhere).
    t = re.sub(r'^(\s*[+\-]?)\(\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*\)',
               lambda m: f"{m.group(1)}{(float(m.group(2)) + float(m.group(3))) / 2:g}", t)

    # Some core-talent lines prefix the stat with its subsystem before the value ("Spirit Magi +30% …").
    # Drop that leading subsystem label so the value is start-anchored for the matchers below; the stat's
    # display name still carries the subsystem, so resolution is unaffected.
    t = re.sub(r'^\s*Spirit Mag(?:i|us)\s+(?=[+\-]?\d)', '', t, flags=re.I)

    # Leading qualifier/scope word before the value ("Additional -30% X", "Enemies +20% X"): move it after
    # the value so the start-anchored matchers see the number first; the word stays for pool/scope matching.
    t = re.sub(r'^(Additional|Enemies)\s+([+\-]?[\d.]+\s*%?)', r'\2 \1', t, flags=re.I)

    # "You can cast N additional Curses" → Max Curses (a flat count; "additional" here means +N, not the
    # damage pool, so the generic matchers would mishandle it).
    m = re.match(r'(?:you can cast\s+)?([\d.]+)\s+additional\s+curses?\b', t, re.I)
    if m:
        return [{"stat_key": "max_curses_flat", "amount": float(m.group(1)), "text": t}]

    # "You can only cast N Curses" → Curse Limit Cap (Hekate's Vision — caps the limit instead of adding).
    m = re.match(r'you can only cast\s+([\d.]+)\s+curses?\b', t, re.I)
    if m:
        return [{"stat_key": "curse_limit_cap_flat", "amount": float(m.group(1)), "text": t}]

    # "You can only deal <Type> Damage" (Extreme Coldness, etc.) → can_only_deal_<type> flag. Offense zeroes any
    # FINAL (post-conversion) damage that isn't an allowed type, so converting to <type> still counts but anything
    # left as another type at the end deals zero.
    m = re.match(r'you can only deal\s+(physical|fire|cold|lightning|erosion)\s+damage\b', t, re.I)
    if m:
        return [{"stat_key": f"can_only_deal_{m.group(1).lower()}", "amount": 1.0, "text": t}]

    # Self-consume drains → typed consume-rate stats (engine.consumption turns these into life/mana/ES per second).
    # Anchored on a LEADING "Consumes" so it never matches consumer lines ("… for every N Life CONSUMED recently").
    # Handles: pct vs flat, current vs Max, Life/Mana/Energy Shield (+ "and <pool>" compound), per-second vs
    # on-skill-use cadence, and "Interval: N s"/"every N s" (per-sec amount = value ÷ N). A "(a-b)" range → midpoint.
    if re.match(r'\s*consumes\s', t, re.I):
        ct = re.sub(r'\(\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*\)',
                    lambda m: f"{(float(m.group(1)) + float(m.group(2))) / 2:g}", t)
        cm = re.match(r'\s*consumes\s+([\d.]+)\s*(%?)\s*(?:of\s+)?(current|max)?\s*'
                      r'(life|mana|energy\s+shield)(?:\s+and\s+(life|mana|energy\s+shield))?(.*)', ct, re.I)
        if cm:
            amt, pct, basis, pool1, pool2, rest = cm.groups()
            val = (float(amt) / 100.0) if pct else float(amt)
            basis_key = ("pct_current" if (basis or "").lower() == "current"
                         else "pct_max") if pct else "flat"
            # Per-event (per-use/cast) vs per-second, and the skill-type SCOPE. "when you use/cast/attack", "on
            # use/cast/attack", "per cast" → per-event (× a use/cast rate). An "Attack(s)/Attack Skills" scope →
            # the ATTACK-skill use rate (counts only attack uses); otherwise generic per-use (any skill). Else
            # per-second / interval. (use-vs-cast nuance is a flagged follow-up; per-event ≈ per-use for now.)
            _per_event = bool(re.search(
                r'\b(?:on\s+(?:skill\s+)?use|on\s+cast|on\s+attack|per\s+cast'
                r'|when\s+(?:you\s+)?(?:use|using|cast|casting|attack|attacking))\b', rest, re.I))
            if _per_event and re.search(r'\battack', rest, re.I):
                cadence = "attack_use"
            elif _per_event:
                cadence = "cast"
            else:
                cadence = "sec"
            iv = re.search(r'(?:interval\s*:?\s*|every\s+)([\d.]+)\s*s', rest, re.I)
            if cadence == "sec" and iv and float(iv.group(1)) > 0:
                val /= float(iv.group(1))
            out = []
            for p in (pool1, pool2):
                if not p:
                    continue
                pk = "energy_shield" if "energy" in p.lower() else p.lower()
                out.append({"stat_key": f"{pk}_consumed_{basis_key}_per_{cadence}", "amount": val, "text": t})
            if out:
                return out

    # Per-N-consumed CONSUMER scalings: "+X% <benefit> for every N <Life|Mana> consumed recently[, up to Y%]"
    # (Tide of the Styx, Compensatory Life, …). NORMALIZE to per-1-unit (X/100 ÷ N) so the consumption loop just
    # multiplies by consumed_recently and caps. Must precede the generic resolver, which would otherwise fuzzy-match
    # the stat's display name and drop the ÷N divisor + cap (silent-wrong). Unhandled benefits (crit, flat phys) have
    # no stat yet → fall through to surface as unresolved (deferred), never mis-resolved.
    m = re.search(r'([\d.]+)\s*%\s*(.+?)\s+for\s+every\s+([\d.]+)\s+(life|mana)\s+consumed\s+recently'
                  r'(?:\s*,?\s*up\s+to\s*([\d.]+)\s*%)?', t, re.I)
    if m:
        _pct, _benefit, _per_n, _pool, _cap = m.groups()
        _b, _p = _benefit.strip().lower(), _pool.lower()
        _stat = ("dmg_additional_per_life_consumed" if (_p == "life" and _b == "damage")
                 else "attack_speed_inc_per_life_consumed" if (_p == "life" and "attack speed" in _b)
                 else "spell_dmg_inc_per_mana_consumed" if (_p == "mana" and "spell damage" in _b)
                 else None)
        if _stat and float(_per_n) > 0:
            out = [{"stat_key": _stat, "amount": (float(_pct) / 100.0) / float(_per_n), "text": t}]
            if _cap:
                out.append({"stat_key": _stat + "_cap", "amount": float(_cap) / 100.0, "text": t})
            return out
    # Range-collapsed copy for the per-N matchers that carry "(a-b)" ranges in the AMOUNT or the divisor N
    # (Glacier "(13-15)-(23-26) … per (1000-1050) Mana"; Tyrant "per (880-900) Mana"; Crimson "(-50–-40)%"). Each
    # paren numeric range → its midpoint (signed, so negative defensive ranges collapse correctly).
    _tc = re.sub(r'\(\s*([+\-]?\d+(?:\.\d+)?)\s*[-–]\s*([+\-]?\d+(?:\.\d+)?)\s*\)',
                 lambda mm: f"{(float(mm.group(1)) + float(mm.group(2))) / 2:g}", t)

    # Flat PHYSICAL damage per N consumed (Blade-dancer's Fingers = Life→Attacks; Glacier Caster Shield =
    # Mana→Attacks+Spells). "Adds A - B Physical Damage to <Attacks|Spells|Attacks and Spells> for every N
    # <Life|Mana> consumed recently. Stacks up to Z." Normalize per-1-unit (flat/N); the "Stacks up to Z" cap is
    # stored as a CONSUMED-AMOUNT cap (Z × N) so one cap clamps min AND max proportionally. Only declared
    # (scope, pool) combos are emitted (attack-life, attack-mana, spell-mana); an undeclared combo → [] (honest NYI).
    m = re.search(r'adds\s+([\d.]+)\s*[-–]\s*([\d.]+)\s+physical\s+damage\s+to\s+'
                  r'(attacks?\s+and\s+spells?|attacks?|spells?)\s+for\s+every\s+([\d.]+)\s+'
                  r'(life|mana)\s+consumed\s+recently(?:\.?\s*stacks?\s+up\s+to\s+([\d.]+))?', _tc, re.I)
    if m:
        _mn, _mx, _scope, _n, _pool, _cap_stacks = m.groups()
        _n = float(_n)
        _pool = _pool.lower()
        if _n > 0:
            _scope = _scope.lower()
            _classes = (["attack", "spell"] if "and" in _scope
                        else ["attack"] if "attack" in _scope else ["spell"])
            _DECLARED = {("attack", "life"), ("attack", "mana"), ("spell", "mana")}
            if all((c, _pool) in _DECLARED for c in _classes):
                out = []
                for c in _classes:
                    out.append({"stat_key": f"physical_{c}_dmg_flat_min_per_{_pool}_consumed",
                                "amount": float(_mn) / _n, "text": t})
                    out.append({"stat_key": f"physical_{c}_dmg_flat_max_per_{_pool}_consumed",
                                "amount": float(_mx) / _n, "text": t})
                if _cap_stacks:
                    out.append({"stat_key": f"physical_dmg_flat_per_{_pool}_consumed_cap",
                                "amount": float(_cap_stacks) * _n, "text": t})
                return out
            return []   # undeclared (scope, pool) combo → honest NYI (don't emit a dead key)

    # Crit per N consumed (Tyrant's Iron Fist): "+X% Critical Strike Rating and Critical Strike Damage for every N
    # Mana consumed recently" → increased Crit Rating + additive Crit Damage, normalized per-1-unit (uncapped).
    m = re.search(r'([\d.]+)\s*%\s*critical\s+strike\s+rating\s+and\s+critical\s+strike\s+damage\s+'
                  r'for\s+every\s+([\d.]+)\s+(life|mana)\s+consumed\s+recently', _tc, re.I)
    if m:
        _pct, _n, _pool = float(m.group(1)), float(m.group(2)), m.group(3).lower()
        if _n > 0 and _pool == "mana":          # only the mana variant is declared (Tyrant)
            _u = (_pct / 100.0) / _n
            return [{"stat_key": "crit_rating_inc_per_mana_consumed", "amount": _u, "text": t},
                    {"stat_key": "crit_dmg_inc_per_mana_consumed", "amount": _u, "text": t}]
        return []                                # undeclared pool → honest NYI

    # Any OTHER "for every N <Life|Mana|ES> consumed recently" consumer (e.g. Compensatory's Mana-Regen-per-consumed)
    # is NOT modeled yet (Stage G). Short-circuit to unresolved (honest NYI) so the generic resolver below can't
    # fuzzy-match the value and apply it ALWAYS — dropping the ÷N divisor + cap (silent-wrong). Uses the range-
    # collapsed copy so a ranged divisor ("for every (880-900) …") is still caught.
    if re.search(r"for\s+every\s+[\d.]+\s+(?:life|mana|energy\s+shield)\s+consumed\s+recently", _tc, re.I):
        return []

    # Compound "+N% Critical Strike Rating and Critical Strike Damage" (Crimson King's gated line; the threshold gate
    # is split off upstream) → BOTH the increased Crit Rating and additive Crit Damage pools. Precedes the generic
    # resolver (which would fuzzy-match only one side). The per-N crit form above already returned if "for every".
    m = re.search(r'([\d.]+)\s*%\s*critical\s+strike\s+rating\s+and\s+critical\s+strike\s+damage', t, re.I)
    if m:
        _v = float(m.group(1)) / 100.0
        return [{"stat_key": "crit_rating_inc", "amount": _v, "text": t},
                {"stat_key": "crit_dmg_inc", "amount": _v, "text": t}]

    # "(-X – -Y)% additional damage taken" (Crimson King's gated defensive line; gate split off upstream). Negative =
    # the WEARER takes less. TRACKED ONLY — folds into the existing dmg_taken_additional pool (like Tenacity
    # blessings) but is NOT wired into any defensive/EHP calc yet (owner: stat tracking only). Skip enemy-vuln phrasings.
    if "enem" not in t.lower():
        m = re.search(r'(-?[\d.]+)\s*%\s*additional\s+damage\s+taken', _tc, re.I)
        if m:
            return [{"stat_key": "dmg_taken_additional", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "+N% additional Curse Effect" → multiplicative Curse Effect pool (e.g. Defile). Must come before the
    # generic Curse Effect matcher so plain "+N% Curse Effect" still maps to the increased pool.
    m = re.search(r'([\d.]+)\s*%\s*additional\s+curse\s+effect', t, re.I)
    if m:
        return [{"stat_key": "curse_effect_additional", "amount": float(m.group(1)) / 100.0, "text": t}]

    # ── Elixir / dew phrasings (Sage Chromatic Shot build) — phrasings the generic resolver can't map ──
    # "+N% Elemental and Erosion Resistance" (Resistance Dew) → split the compound name into both pools.
    # ("Elemental" = Fire/Cold/Lightning, carried by elemental_resistance; erosion_resistance is separate.)
    m = re.match(r'[+\-]?\s*([\d.]+)\s*%\s*elemental\s+and\s+erosion\s+resistance\b', t, re.I)
    if m:
        v = float(m.group(1)) / 100.0
        return [{"stat_key": "elemental_resistance", "amount": v, "text": t},
                {"stat_key": "erosion_resistance", "amount": v, "text": t}]

    # "+N% Movement Speed, up to +M%" (Swiftness / Scorpion Stinger) → movement_speed_inc. The "up to +M%" is a
    # soft per-source cap; we model the base bonus (full uptime) and drop the cap clause.
    m = re.match(r'[+\-]?\s*([\d.]+)\s*%\s*movement\s+speed\s*,?\s*up\s+to\b', t, re.I)
    if m:
        return [{"stat_key": "movement_speed_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "Adds N% of Max Life to Energy Shield" (Tortoise Shell) → max_life_as_es_pct (derive.py folds it into the ES
    # flat pool after Max Life is computed, so it then scales with ES inc/additional).
    m = re.match(r'adds\s+([\d.]+)\s*%\s*of\s+max\s+life\s+to\s+energy\s+shield\b', t, re.I)
    if m:
        return [{"stat_key": "max_life_as_es_pct", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "Half of the damage taken bypasses Energy Shield" (Tortoise Shell) → es_bypass_pct FLAG. Surfaced now; the
    # actual bypass awaits the defensive damage-taken pass. "Half" = 50% when no explicit number is present.
    if re.search(r'damage\s+taken\s+bypasses\s+energy\s+shield', t, re.I):
        m2 = re.search(r'([\d.]+)\s*%', t)
        return [{"stat_key": "es_bypass_pct", "amount": float(m2.group(1)) if m2 else 50.0, "text": t}]

    # "-N% Cursed Effect" bare form (Putrid Toad, Blur-gated) → curse_effect_against_inc (effect of curses on YOU;
    # negative = less effective). Require the "d" in "Cursed" — "Curse Effect" (no d) is your OWN curse
    # effectiveness (curse_effect_inc) and must NOT be caught here. The "…against you" phrasing maps via the dict.
    m = re.match(r'\s*([+\-]?[\d.]+)\s*%\s*cursed\s+effect\b', t, re.I)
    if m:
        return [{"stat_key": "curse_effect_against_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "Energy Shield Charge … cannot be interrupted by damage" (White Rhino) → es_uninterruptible flag (surfaced;
    # no numeric effect until ES-recharge timing is modeled — stops reading as NYI).
    if re.search(r'energy\s+shield\s+charge\b.*\bcannot\s+be\s+interrupted', t, re.I):
        return [{"stat_key": "es_uninterruptible", "amount": 1.0, "text": t}]

    # "Damage triggers Lucky" (Thunder Wood) → lucky on every damage type (offense rolls each type's range twice
    # and takes the higher). All five lucky_<type> stats exist; offense applies them per type.
    if re.search(r'\bdamage\s+triggers\s+lucky\b', t, re.I):
        return [{"stat_key": f"lucky_{ty}", "amount": 1.0, "text": t}
                for ty in ("physical", "fire", "cold", "lightning", "erosion")]

    # "N% [additional] Attack and Cast Speed" → BOTH attack & cast speed (same pool). Explicit because the
    # generic single-stat resolver only catches "Cast Speed" and silently drops the Attack half (Quick Decision /
    # Quick Mobility). Excludes scoped forms ("Minion …", "Warcry …") by anchoring at the value.
    m = re.match(r'[+\-]?\s*([\d.]+)\s*%\s*(additional\s+)?attack and cast speed\b', t, re.I)
    if m:
        pool = "additional" if m.group(2) else "inc"
        amt = float(m.group(1)) / 100.0
        return [{"stat_key": f"attack_speed_{pool}", "amount": amt, "text": t},
                {"stat_key": f"cast_speed_{pool}", "amount": amt, "text": t}]

    # "Has Dormant Entanglement" (Acquaintance core talent / gear) → flag enabling Dormant Entanglement's
    # per-inactivated-tangle bonus (read in compute._offense_for_slot). No value in the text → amount 1.0.
    if re.search(r'\bhas\s+dormant\s+entanglement\b', t, re.I):
        return [{"stat_key": "has_dormant_entanglement_flag", "amount": 1.0, "text": t}]

    # "N% chance … to inflict M additional stack(s) of Wilt" → distinct stat from plain Wilt chance (chance for
    # an EXTRA stack, a separate mechanic — owner-confirmed). Must precede any generic Wilt-chance match.
    m = re.search(r'([\d.]+)\s*%\s*chance\b.*?\binflict\s+\d+\s+additional\s+stacks?\s+of\s+wilt', t, re.I)
    if m:
        return [{"stat_key": "wilt_additional_stack_chance", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Beam supports: "+N additional Beams/refractions" → extra count; "+N% additional Beam Length" → length.
    m = re.search(r'([\d.]+)\s+additional\s+(?:beams|refractions)\b', t, re.I)
    if m:
        return [{"stat_key": "extra_beams_flat", "amount": float(m.group(1)), "text": t}]
    m = re.search(r'([\d.]+)\s*%\s*additional\s+beam\s+length\b', t, re.I)
    if m:
        return [{"stat_key": "beam_length_additional", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "+N to Max Summonable Minions" / "+N Max … Minions" → additional max minions (count).
    m = re.search(r'([\d.]+)\s+(?:to\s+)?max\s+summonable\s+minions\b', t, re.I)
    if m:
        return [{"stat_key": "extra_max_minions_flat", "amount": float(m.group(1)), "text": t}]

    # "Damage Penetrates N% <type> Resistance" (pact-spirit pen nodes) — value sits mid-phrase, so the
    # start-anchored matchers below miss it. Maps to the player {type}_pen stat (elemental → elemental_pen).
    m = re.match(r'damage\s+penetrates\s+([\d.]+)\s*%\s*'
                 r'(elemental|fire|cold|lightning|erosion)\s+resistance', t, re.I)
    if m:
        typ = m.group(2).lower()
        stat = "elemental_pen" if typ == "elemental" else f"{typ}_pen"
        return [{"stat_key": stat, "amount": float(m.group(1)) / 100.0, "text": t}]

    # Outgoing damage-type conversion: "Adds/Converts N% [of] <A> Damage as/to <B> Damage" (the value sits
    # after the verb, so the start-anchored matchers below would miss it). "Adds"/"as" → adds-as key;
    # "Converts"/"to" → convert key. Only valid up the priority chain (phys→light→cold→fire→erosion).
    m = re.match(r'(adds|converts)\s+([\d.]+)\s*%\s*(?:of\s+)?'
                 r'(physical|lightning|cold|fire|erosion)\s+damage\s+(?:as|to)\s+'
                 r'(physical|lightning|cold|fire|erosion)\s+damage', t, re.I)
    if m:
        verb, val, src, dst = m.group(1).lower(), float(m.group(2)), m.group(3).lower(), m.group(4).lower()
        order = ["physical", "lightning", "cold", "fire", "erosion"]
        if order.index(dst) > order.index(src):           # up-chain only
            key = f"{src}_convert_to_{dst}" if verb == "converts" else f"{src}_as_{dst}"
            return [{"stat_key": key, "amount": val / 100.0, "text": t}]
        return []

    # Arcane: "Converts N% of Mana Cost to Life Cost" — active-skill cost paid as life (cost mechanic,
    # tracked; needs skill-cost modeling to do anything).
    m = re.match(r'converts\s+([\d.]+)\s*%\s*of\s+mana\s+cost\s+to\s+life\s+cost', t, re.I)
    if m:
        return [{"stat_key": "mana_cost_to_life_cost", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Ward: "Adds N% of Sealed Mana/Life as Energy Shield" — flat Max ES = coeff × raw sealed pool (needs
    # sealed mana/life modeling).
    m = re.match(r'adds\s+([\d.]+)\s*%\s*of\s+sealed\s+(mana|life)\s+as\s+energy\s+shield', t, re.I)
    if m:
        return [{"stat_key": f"energy_shield_per_sealed_{m.group(2).lower()}", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Joined Force: "Adds N% of the damage of the Off-Hand Weapon to the final damage of the Main-Hand Weapon"
    # — off-hand becomes a stat-stick; N% of its fully-scaled damage adds to main-hand FINAL (needs separate
    # main/off-hand weapon damage modeling).
    m = re.match(r'adds\s+([\d.]+)\s*%\s*of\s+the\s+damage\s+of\s+the\s+off-?hand\s+weapon', t, re.I)
    if m:
        return [{"stat_key": "joined_force_offhand_dmg", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Defensive damage-taken conversion: "Converts N% of <A> Damage taken to <B> Damage" (the "taken" is what
    # distinguishes it from outgoing). Needs the incoming-damage/EHP model to do anything (tracked for now).
    m = re.match(r'converts\s+([\d.]+)\s*%\s*of\s+(physical|lightning|cold|fire|erosion)\s+damage\s+taken\s+to\s+'
                 r'(physical|lightning|cold|fire|erosion)\s+damage', t, re.I)
    if m:
        return [{"stat_key": f"{m.group(2).lower()}_taken_as_{m.group(3).lower()}_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Rebirth: "Converts N% of <Life|Energy Shield> Regain to Restoration Over Time" — needs Regain. The
    # shared-stat splitter separates "Life Regain and Energy Shield Regain", so match each pool segment.
    m = re.match(r'converts\s+([\d.]+)\s*%\s*of\s+(life|energy\s+shield)\s+regain\s+to\s+restoration', t, re.I)
    if m:
        pool = "es" if m.group(2).lower().startswith("energy") else "life"
        return [{"stat_key": f"{pool}_regain_to_restoration", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Co-resonance: share Attack/Cast Speed (inc + additional) onto Sentry Cast Frequency — needs Sentry impl.
    m = re.match(r'(attack|cast)\s+speed\s+bonus\s+and\s+.*additional\s+bonus\s+are\s+also\s+applied\s+to', t, re.I)
    if m:
        which = m.group(1).lower()
        key = "attack_speed_to_attack_sentry_cast_freq" if which == "attack" else "cast_speed_to_spell_sentry_cast_freq"
        return [{"stat_key": key, "amount": 1.0, "text": t}]

    # Play Safe: "N% of the bonuses and additional bonuses to Cast Speed is also applied to Spell Burst Charge
    # Speed" — flag (1.0 = full share); the aggregator propagates cast-speed inc + each additional.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+bonuses\s+and\s+additional\s+bonuses\s+to\s+cast\s+speed\s+is\s+also\s+applied\s+to\s+spell\s+burst', t, re.I)
    if m:
        return [{"stat_key": "cast_speed_to_spell_burst_charge", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Spell Burst flat hit-damage pool: "+N% additional Hit Damage for skills cast by Spell Burst [when Spell
    # Burst is activated by the supported skill]" (Psychic Burst, Moon Strike: Wax and Wane, the Burst Activation
    # penalty). The trailing "when …" clause is always-true in burst mode, so it's dropped. `$`-anchored so the
    # RAMPED variants ("for every 1 stack(s) … consumed" / "each time … Stacks up to N") do NOT match here —
    # those scale with stacks and are hand-modeled per-support in compute._offense_for_slot (§7). Carries the
    # spell_burst tag → applies only in burst mode.
    m = re.match(r'([+\-]?[\d.]+)\s*%\s*additional\s+hit\s+damage\s+for\s+skills\s+cast\s+by\s+spell\s+burst'
                 r'(?:\s+when\s+spell\s+burst\s+is\s+activated\s+by\s+the\s+supported\s+skill)?\s*$', t, re.I)
    if m:
        return [{"stat_key": "spell_burst_hit_dmg_additional", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Surging Inspiration: "+N% chance to immediately gain M stack(s) of Spell Burst Charge when using a skill"
    # → expected stacks gained per cast (chance × stacks). Feeds the alternative-fill path in offense (Surging
    # can top Spell Burst to max faster than the base 2s charge). Shape flagged for in-game verification.
    m = re.match(r'[+\-]?\s*([\d.]+)\s*%\s*chance\s+to\s+immediately\s+gain\s+([\d.]+)\s*stack\(?s?\)?\s+of\s+spell\s+burst\s+charge', t, re.I)
    if m:
        return [{"stat_key": "spell_burst_chance_gain_stacks_flat",
                 "amount": (float(m.group(1)) / 100.0) * float(m.group(2)), "text": t}]

    # Insatiable Greed: "N% of the bonuses to Attack Speed is also applied to Spell Burst Charge Speed" — coefficient
    # (1.5); the aggregator propagates each attack-speed source × coeff into the charge-speed pools (like Play Safe).
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+bonuses\s+to\s+attack\s+speed\s+is\s+also\s+applied\s+to\s+spell\s+burst', t, re.I)
    if m:
        return [{"stat_key": "attack_speed_to_spell_burst_charge", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Burst Activation (support): "When Spell Burst is fully charged, triggers the supported skill … attempts to
    # trigger the supported skill's Spell Burst" → unconditional auto-trigger flag (badges Consumed via the support).
    m = re.match(r'when\s+spell\s+burst\s+is\s+fully\s+charged.*spell\s+burst', t, re.I)
    if m:
        return [{"stat_key": "spell_burst_auto_trigger_flag", "amount": 1.0, "text": t}]

    # Solid River: "When Burst Charge Recovery Speed is at least N% of the base value, reaching the Max Spell Burst
    # Charge triggers … attempts to activate the Main Spell Skill's Spell Burst" → CONDITIONAL auto-trigger: the
    # charge-factor threshold (N/100). offense enables auto only when charge_factor ≥ threshold. The trailing
    # "-30% Movement Speed" splits off as its own line.
    m = re.match(r'when\s+burst\s+charge\s+recovery\s+speed\s+is\s+at\s+least\s+\(?([\d.]+)(?:\s*[-–]\s*([\d.]+))?\)?\s*%.*spell\s+burst', t, re.I)
    if m:
        lo = float(m.group(1)); hi = float(m.group(2)) if m.group(2) else lo
        return [{"stat_key": "spell_burst_auto_charge_threshold", "amount": (lo + hi) / 200.0, "text": t}]

    # Solid River: "For every +X% Spell Burst Charge Speed, +Y% additional Hit Damage for skills cast by Spell Burst,
    # up to +Z%" → stepwise charge-speed→burst-damage scaling (per X / bonus Y / cap Z). Mid-text ranges aren't
    # collapsed upstream (only leading ranges are), so capture them here.
    m = re.match(r'for\s+every\s+\+?\(?([\d.]+)(?:\s*[-–]\s*([\d.]+))?\)?\s*%\s*spell\s+burst\s+charge\s+speed,?\s*'
                 r'\+?\(?([\d.]+)(?:\s*[-–]\s*([\d.]+))?\)?\s*%\s*additional\s+hit\s+damage\s+for\s+skills\s+cast\s+by\s+spell\s+burst.*'
                 r'up\s+to\s+\+?([\d.]+)\s*%', t, re.I)
    if m:
        per = (float(m.group(1)) + (float(m.group(2)) if m.group(2) else float(m.group(1)))) / 200.0
        bonus = (float(m.group(3)) + (float(m.group(4)) if m.group(4) else float(m.group(3)))) / 200.0
        cap = float(m.group(5)) / 100.0
        return [{"stat_key": "charge_speed_to_spell_burst_hit_dmg", "amount": bonus, "text": t},
                {"stat_key": "charge_speed_to_spell_burst_hit_dmg_per", "amount": per, "text": t},
                {"stat_key": "charge_speed_to_spell_burst_hit_dmg_cap", "amount": cap, "text": t}]

    # "+N to Max Spell Burst" (the "to" variant, e.g. Squidnova's "+1 to Max Spell Burst") → max_spell_burst_flat.
    m = re.match(r'\+?\s*([\d.]+)\s+to\s+max\s+spell\s+burst\b', t, re.I)
    if m:
        return [{"stat_key": "max_spell_burst_flat", "amount": float(m.group(1)), "text": t}]

    # "+N% Squidnova Effect" → buff-effect multiplier scaling the Squidnova-sourced spell damage.
    m = re.match(r'[+\-]?\s*([\d.]+)\s*%\s*squidnova\s+effect\b', t, re.I)
    if m:
        return [{"stat_key": "squidnova_effect_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Squiddle source line: "Activating Spell Burst with at least N stack(s) of Max Spell Burst grants … Squidnova"
    # → marker flag so compute can auto-enable the has_squidnova condition when Squiddle is equipped.
    m = re.match(r'activating\s+spell\s+burst\s+with\s+at\s+least\s+[\d.]+\s+stack\(?s?\)?\s+of\s+max\s+spell\s+burst\s+grants.*squidnova', t, re.I)
    if m:
        return [{"stat_key": "has_squidnova_flag", "amount": 1.0, "text": t}]

    # Gale: "N% of the Projectile Speed bonus is also applied to the additional bonus for Projectile Damage"
    # — coefficient on increased projectile speed → additional projectile damage (own factor; aggregator).
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+projectile\s+speed\s+bonus\s+is\s+also\s+applied\s+to\s+the\s+additional\s+bonus\s+for\s+projectile\s+damage', t, re.I)
    if m:
        return [{"stat_key": "proj_speed_to_proj_dmg", "amount": float(m.group(1)) / 100.0, "text": t}]

    # True Flame: "N% of the additional bonus to Damage Over Time taken from Affliction is also applied to your
    # Fire Hit Damage" (lead "When an enemy is Ignited" splits off as the gate). Inert until Affliction modeled.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+additional\s+bonus\s+to\s+damage\s+over\s+time\s+taken\s+from\s+affliction\s+is\s+also\s+applied\s+to\s+your\s+fire\s+hit\s+damage', t, re.I)
    if m:
        return [{"stat_key": "affliction_dot_to_fire_hit", "amount": float(m.group(1)) / 100.0, "text": t}]

    # United Stand (2nd line): "N% of the Life and Energy Shield Regain Effect of Synthetic Troop Minions is
    # also applied to you" — fraction of minion regain shared to the player. Needs Regain + testing.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+life\s+and\s+energy\s+shield\s+regain\s+effect\s+of\s+synthetic\s+troop\s+minions\s+is\s+also\s+applied\s+to\s+you', t, re.I)
    if m:
        return [{"stat_key": "minion_regain_shared_to_player", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "Adds N-N Base <Ignite|Wilt|Trauma|Ailment> Damage [to Minions]" → that ailment's flat base damage pool.
    m = re.match(r'adds\s+([\d.]+)\s*-\s*([\d.]+)\s+base\s+(ignite|wilt|trauma|ailment)\s+damage', t, re.I)
    if m:
        lo, hi, kind = float(m.group(1)), float(m.group(2)), m.group(3).lower()
        return [{"stat_key": f"{kind}_dmg_flat_min", "amount": lo, "text": t},
                {"stat_key": f"{kind}_dmg_flat_max", "amount": hi, "text": t}]

    # "Minions' Multistrikes deal N% increasing damage" → MINION stat (NYI for player DPS). Checked FIRST so the
    # minion line never falls through to the player increment below (that double-counted, e.g. Quick Advancement).
    m = re.match(r'minions\'?\s+multistrikes?\s+deal\s+([\d.]+)\s*%\s*increasing\s+damage', t, re.I)
    if m:
        return [{"stat_key": "minion_multistrike_increasing_dmg_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "Multistrikes [of the supported skill] deal N% increasing damage" → per-stack Multistrike Damage Increment.
    m = re.match(r'multistrikes?\s+(?:of\s+the\s+supported\s+skill\s+)?deal\s+([\d.]+)\s*%\s*increasing\s+damage', t, re.I)
    if m:
        return [{"stat_key": "multistrike_increasing_dmg_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "+N% additional Multistrike Damage Increment" → multiplies the base increment (NOT the increment itself).
    m = re.search(r'([\d.]+)\s*%\s*additional\s+multistrike\s+damage\s+increment', t, re.I)
    if m:
        return [{"stat_key": "multistrike_increasing_dmg_additional", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "+N% chance [for the supported skill] to trigger Multistrike" / "+N% Multistrike Chance" → Multistrike Chance.
    m = re.search(r'([\d.]+)\s*%\s*chance\s+(?:for\s+the\s+supported\s+skill\s+)?to\s+trigger\s+multistrike', t, re.I)
    if not m:
        # Anchored fallback for "+N% Multistrike Chance" GRANTS only — must start the line, so mid-line
        # references like "… for every 1% Multistrike chance" (a scaling basis, not a grant) don't match.
        m = re.match(r'\+?\s*([\d.]+)\s*%\s*multistrike\s+chance\b', t, re.I)
    if m:
        return [{"stat_key": "multistrike_chance", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "+N% additional Base Damage for Two-Handed Weapons" → tracked (deferred additional pool).
    m = re.match(r'([\d.]+)\s*%\s*additional\s+base\s+damage\s+for\s+two-?handed\s+weapons', t, re.I)
    if m:
        return [{"stat_key": "two_handed_base_dmg_additional", "amount": float(m.group(1)) / 100.0, "text": t}]

    # "+N Command per second" → flat Command/sec (tracked; Command subsystem NYI).
    m = re.match(r'\+?\s*([\d.]+)\s+command\s+per\s+second', t, re.I)
    if m:
        return [{"stat_key": "command_per_second_flat", "amount": float(m.group(1)), "text": t}]

    # "+N Affliction inflicted per second by Minions" → flat (tracked; minion subsystem NYI).
    m = re.match(r'\+?\s*([\d.]+)\s+affliction\s+inflicted\s+per\s+second\s+by\s+minions', t, re.I)
    if m:
        return [{"stat_key": "minion_affliction_per_second_flat", "amount": float(m.group(1)), "text": t}]

    # "N% of the bonuses for Movement Speed is also applied to <Attack/Cast Speed | Cooldown Recovery Speed>"
    # — coefficient; aggregator propagates movement_speed_inc × coeff onto the target.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+bonuses?\s+for\s+movement\s+speed\s+is\s+also\s+applied\s+to\s+(?:the\s+)?(attack\s+speed|cast\s+speed|cooldown\s+recovery\s+speed)', t, re.I)
    if m:
        tgt = {"attack speed": "attack_speed", "cast speed": "cast_speed",
               "cooldown recovery speed": "cdr"}[re.sub(r'\s+', ' ', m.group(2).lower())]
        return [{"stat_key": f"movement_bonus_to_{tgt}", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Probabilistic damage ("…N% chance for that cast to deal +M% additional damage") → expected value.
    # Emit one dmg_additional = (N/100)×(M/100) with a SHARED text so a talent's mutually-exclusive tiers
    # pool ADDITIVELY into one factor (offense sums same-identity positives), never multiply.
    m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*chance\b.*?\bdeal\s*\+?(\d+(?:\.\d+)?)\s*%\s*additional\s+damage', t, re.I)
    if m:
        ev = (float(m.group(1)) / 100.0) * (float(m.group(2)) / 100.0)
        return [{"stat_key": "dmg_additional", "amount": ev,
                 "text": "probabilistic additional damage (expected value)"}]

    # "You can apply N additional Tangle(s) to enemies" → flat +N Tangles applied (mirrors the curses form).
    m = re.match(r'(?:you can\s+)?apply\s+([\d.]+)\s+additional\s+tangles?\b', t, re.I)
    if m:
        return [{"stat_key": "extra_tangle_applied_flat", "amount": float(m.group(1)), "text": t}]

    # Trailing flat count: "<Stat Name> +N" (Max Sentry Quantity +1, Min Channeled Stacks +1). Resolve the
    # value-stripped name; accept ONLY a *_flat stat so a stray "+N" can never land in a % pool.
    m = re.match(r'^(.+?)\s+([+\-]\d+(?:\.\d+)?)\s*$', t)
    if m and '%' not in t:
        stat_key, _u = _resolve_gear_stat(m.group(1).strip())
        if stat_key and stat_key.endswith('_flat'):
            return [{"stat_key": stat_key, "amount": float(m.group(2)), "text": t}]

    # "Adds N-N <Type> Damage to Attacks/Spells/Attacks and Spells" → flat added damage min+max.
    m = _CUSTOM_ADDS_RE.match(t)
    if m:
        lo, hi, dtype, dest = float(m.group(1)), float(m.group(2)), m.group(3).lower(), m.group(4).lower()
        dests = ["attack", "spell"] if dest == "attacks and spells" else (["attack"] if dest == "attacks" else ["spell"])
        out: list[dict] = []
        for d in dests:
            out.append({"stat_key": f"{dtype}_{d}_dmg_flat_min", "amount": lo, "text": t})
            out.append({"stat_key": f"{dtype}_{d}_dmg_flat_max", "amount": hi, "text": t})
        return out

    # Range: "50-80 fire attack damage"
    m = _CUSTOM_RANGE_RE.match(t)
    if m:
        val_min = float(m.group(1))
        val_max = float(m.group(2))
        desc = _normalize_for_custom_resolve(m.group(3).strip())
        stat_key, _unit = _resolve_gear_stat(desc)
        if stat_key:
            if stat_key.endswith("_min"):
                base = stat_key[:-4]
                return [
                    {"stat_key": base + "_min", "amount": val_min, "text": t},
                    {"stat_key": base + "_max", "amount": val_max, "text": t},
                ]
            if stat_key.endswith("_max"):
                base = stat_key[:-4]
                return [
                    {"stat_key": base + "_min", "amount": val_min, "text": t},
                    {"stat_key": base + "_max", "amount": val_max, "text": t},
                ]
            avg = (val_min + val_max) / 2.0
            return [{"stat_key": stat_key, "amount": avg, "text": t}]
        return []

    # Single value: "10% additional attack damage" or "500 attack crit rating flat"
    m = _CUSTOM_SINGLE_RE.match(t)
    if m:
        val = float(m.group(1))
        is_pct = bool(m.group(2))
        normalized = _normalize_for_custom_resolve(t)
        stat_key, _unit = _resolve_gear_stat(normalized)
        if stat_key:
            amount = val / 100.0 if is_pct else val
            return [{"stat_key": stat_key, "amount": amount, "text": t}]

    return []
