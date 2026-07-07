"""Modifier-line boundary helpers — the ONE pattern for consuming stored modifier lines.

The scraper (tlidb-scraper) mints a language-independent identity on every modifier line
(`pooling_uuid = uuid5(NAMESPACE, affix_identity(text))`, see docs/BUILDER_HANDOFF_IDENTITY.md in the
scraper repo and tests/test_scraper_parity_gate.py). Imported catalogs store each line as a SLIM dict:

    {"text": str, "uuid": str|None, "pooling_uuid": str|None, "modifier_id": str|None}

Consumers keep operating on plain strings: unwrap with `line_text`/`line_texts` at the boundary and
never reach into the dict elsewhere. The identity fields are read only by the pooling/identity layer
(`line_pooling_uuid`) and the cross-check tests.

Every helper accepts `str | dict | None` FOREVER — old saved builds embed string-shaped lines (e.g.
slate slot effects copied before this migration), and hand-written override lines stay plain strings.
"""
from __future__ import annotations

import uuid as _uuid

# Shared mint namespace — hardcoded forever, scraper-side and here (matched pair with the scraper's
# canonical_template; neither may change alone).
NAMESPACE = _uuid.UUID("4d8c3c25-940d-453e-be66-21a9d603aa0e")

# The four keys of a stored slim line. `template`/`clauses`/`text_by_lang` from the scraper's full
# ModifierLine are deliberately NOT stored (recomputable / deferred to the localization pass).
SLIM_KEYS = ("text", "uuid", "pooling_uuid", "modifier_id")


def line_text(x) -> str:
    """The display/parse text of a modifier line (str, slim dict, or scraper ModifierLine)."""
    if isinstance(x, dict):
        return x.get("text") or ""
    return x or ""


def line_texts(xs) -> list[str]:
    """Unwrap a list of modifier lines to plain texts (None-safe)."""
    return [line_text(x) for x in (xs or [])]


def line_pooling_uuid(x) -> str | None:
    """The minted pooling identity of a line, or None for plain strings / unminted lines."""
    if isinstance(x, dict):
        return x.get("pooling_uuid") or None
    return None


def slim(x, text: str | None = None) -> dict:
    """Slim stored form of a scraper ModifierLine (or plain string → uuid-less slim dict).

    `text` overrides the stored text while keeping the ids — for value-only transforms
    (fraction normalization etc.) that don't change the line's identity. Wording-CHANGING
    transforms must not carry ids: build those lines with `slim(raw_wording_string)` instead
    (tests/test_identity_crosscheck.py enforces uuid == uuid5(NAMESPACE, affix_identity(text))).
    """
    if isinstance(x, dict):
        return {
            "text": text if text is not None else (x.get("text") or ""),
            "uuid": x.get("uuid"),
            "pooling_uuid": x.get("pooling_uuid"),
            "modifier_id": x.get("modifier_id"),
        }
    return {
        "text": text if text is not None else (x or ""),
        "uuid": None,
        "pooling_uuid": None,
        "modifier_id": None,
    }


def slim_checked(x, text: str) -> dict:
    """`slim(x, text)`, but the ids carry ONLY if the transformed text still recomputes to the line's
    minted pooling_uuid — i.e. the transform was provably value-only under affix_identity. Use for any
    import-time text transform (fraction normalization, tier collapse): a wording-changing transform
    silently degrades to a uuid-less line instead of storing a lying identity."""
    from engine.affix_identity import affix_identity  # deferred: keep module import cheap

    out = slim(x, text)
    pu = out.get("pooling_uuid")
    if pu and str(_uuid.uuid5(NAMESPACE, affix_identity(text))) != pu:
        out["uuid"] = None
        out["pooling_uuid"] = None
    return out
