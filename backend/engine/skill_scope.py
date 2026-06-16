"""Shared skill-type scope detection for "+X% <stat> for/dealt by <SkillType> Skills" modifiers.

Used by BOTH the unified resolver (server._parse_custom_mod_text) AND the pact-spirit/hero-memory resolver
(engine.aggregator), so the two paths can't drift. Strips a recognized scope qualifier and returns its tag;
the residual is resolved to the BASE stat by each caller's normal lookup, and the contribution is then
restricted to skills carrying that tag (BuildSource.add_scoped / materialize_for_skill).
"""
import re

# The skill word maps 1:1 to a real skill.tags value (SS12 _skills.json). Unknown word ⇒ not a recognized
# scope ⇒ left untouched (never silently broadened to all skills). "triggered" omitted (not a real tag).
_SKILL_TYPE_TAG = {
    "attack": "attack", "spell": "spell", "melee": "melee", "projectile": "projectile", "area": "area",
    "channeled": "channeled", "sentry": "sentry", "mobility": "mobility", "focus": "focus",
    "barrage": "barrage", "restoration": "restoration", "combo": "combo", "demolisher": "demolisher",
    "ranged": "ranged", "enhanced": "enhanced skill",  # tag literal has a space
}
_SKILL_SCOPE_RE = re.compile(r'\s+(?:for|dealt by)\s+([A-Za-z]+)\s+skills\b', re.I)
# "chance for <X> Skills to deal Double/Triple/Quadruple Damage" — scope mid-phrase, not a clean suffix.
_SCOPE_MULTI_RE = re.compile(
    r'chance\s+for\s+([A-Za-z]+)\s+skills\s+to\s+deal\s+(double|triple|quadruple)\s+damage', re.I)


# INLINE skill-type scope: the type word sits directly before the stat noun, optionally with a "Skill"
# filler — "Melee Skill Damage", "Melee Attack Speed", "Projectile Cast Speed". The suffix detector below
# ("… for/dealt by X Skills") misses these, and the base resolver chokes on the extra word(s). Used ONLY as
# a FALLBACK after normal resolution fails (server._parse_custom_mod_text), so it never overrides the
# typed-stat path — "additional Melee Damage" still resolves to melee_dmg_additional on the first, no-peel try.
_INLINE_SCOPE_RE = re.compile(
    r'\b(' + '|'.join(sorted(_SKILL_TYPE_TAG, key=len, reverse=True)) + r')\s+(?:skill\s+)?', re.I)


def detect_inline_skill_scope(text: str) -> tuple[str, str | None]:
    """Peel a leading inline skill-type qualifier ("Melee Skill " / "Melee ") and return (residual, tag),
    or (text, None) if no recognized type word is present. Caller resolves the residual to the base stat and
    scopes the result to `tag` (so "Melee Attack Speed" → attack_speed_inc scoped melee)."""
    m = _INLINE_SCOPE_RE.search(text)
    if not m:
        return text, None
    tag = _SKILL_TYPE_TAG.get(m.group(1).lower())
    if not tag:
        return text, None
    residual = re.sub(r'\s{2,}', ' ', (text[:m.start()] + text[m.end():]).strip())
    return residual, tag


def detect_skill_scope(text: str) -> tuple[str, str | None]:
    """Return (residual_text_to_resolve, scope_tag|None). Strips a recognized 'for/dealt by <X> Skills'
    qualifier; unknown skill words are left in place (scope None → resolves/badges exactly as today)."""
    m = _SCOPE_MULTI_RE.search(text)
    if m:
        tag = _SKILL_TYPE_TAG.get(m.group(1).lower())
        if tag:
            # Replace in place so the leading value survives: "+5 % Triple Damage Chance".
            return (_SCOPE_MULTI_RE.sub(f"{m.group(2).capitalize()} Damage Chance", text), tag)
    m = _SKILL_SCOPE_RE.search(text)
    if m:
        tag = _SKILL_TYPE_TAG.get(m.group(1).lower())
        if tag:
            return (text[:m.start()] + text[m.end():], tag)   # excise suffix; resolve the residual
    return (text, None)
