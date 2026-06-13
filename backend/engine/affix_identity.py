"""Affix-identity normalization — the pooling key for per-affix "additional" damage.

Two contributions are "the same affix" iff their wording matches after the rolled value(s) are
stripped and whitespace/case are normalized. This is the identity used to decide whether two
`additional`-damage contributions SUM (same affix) or MULTIPLY (distinct affixes) — see
docs/ADDITIONAL_DAMAGE_POOLING.md.

It must reduce all of these real wordings to the SAME skeleton "additional attack damage":
    "+8 % additional Attack Damage"            (talent recipe text — fixed value)
    "+(8–10) % additional Attack Damage"       (gear raw_text — range, en-dash)
    "-5 % additional Attack Damage"            (negative roll)
so it is deliberately more robust than tools.node_type_filter_builder._override_key (which only
sees fixed-value talent text and is left unchanged to avoid altering the filter builder).
"""
from __future__ import annotations
import re

# A "value token": optional sign, optional '(' , a number (optionally a range and/or decimals),
# optional ')', optional trailing '%'. Covers "+8", "-5%", "+(8–10) %", "(20–30)", "1.5".
# Dash class includes ASCII hyphen and common unicode dashes used in game ranges.
_VALUE_RE = re.compile(
    r"[+\-‒–—]?\s*\(?\s*\d[\d.,]*\s*"
    r"(?:[-‒–—]\s*\d[\d.,]*\s*)?\)?\s*%?"
)


def affix_identity(text: str) -> str:
    """Return a stable identity key for an affix text (value-stripped, lowercased, ws-collapsed).

    Also drops leftover value formatting — the `#` template placeholder (from `expression` fields),
    stray `+`/`%`, and parens — so the template form `+(#) % additional X` and a rolled
    `+(20–30) % additional X` collapse to the same identity.
    """
    s = _VALUE_RE.sub(" ", (text or "").lower())
    # Drop all punctuation/symbols (#, %, +, '.', ',', '/', parens, …) so formatting variants of the
    # same affix collapse — e.g. "+35 % additional Cold Damage" and "16% additional Cold Damage.".
    # Keep word characters and the ASCII hyphen ("one-handed weapon", "off-hand").
    s = re.sub(r"[^\w\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
