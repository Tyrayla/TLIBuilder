"""<Hero> — <Trait Name> (trait_id "<trait_id>").

<One-paragraph summary: the trait's payoff, what scales it, what's user-set vs informational.>
Values are the SS12 `_hero_traits.json` constants, indexed by trait tier (level 1-5 -> index 0-4). Advanced
"pick-one" traits apply only when selected.
"""
from __future__ import annotations

TRAIT_ID = "<trait_id>"

# ── Constants by tier (1-5 -> index 0-4) ────────────────────────────────────────
# _SOME_LINE = [v1, v2, v3, v4, v5]


def _contrib(stat_key, amount, text, source):
    return {"stat_key": stat_key, "amount": amount, "text": text, "source": source}


def _tier(slot_levels, idx):
    """0-based tier index (level-1) for slot `idx`, clamped to 0-4. abs() so a disabled (negative) level still
    resolves its remembered tier."""
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return max(0, min(4, int(abs(lvl)) - 1))


def _enabled(slot_levels, idx):
    """A node/tier is DISABLED when its slot level is < 1 (the UI stores a disabled node as a negative level)."""
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return lvl >= 1


def _flag(condition_state, key, default):
    v = condition_state.get(key, default)
    return bool(v) if v is not None else default


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    contribs: list[dict] = []

    base_lvl = slot_levels[0] if slot_levels else 1
    # Read user-set conditions, e.g.:
    # some_input = float(condition_state.get("<condition_key>", <default>))

    # ── Base (slot 0) ─ gate on _enabled so right-click disable works ───────────
    if _enabled(slot_levels, 0):
        # contribs.append(_contrib("<stat>", <amount>, "<text>", "<Trait Name>"))
        # if abs(base_lvl) >= 5: ...Artificial Moon...
        pass

    # ── <Pick A> (unlock 45, slot 1) ────────────────────────────────────────────
    # if "<Pick A>" in picks and _enabled(slot_levels, 1):
    #     t = _tier(slot_levels, 1)
    #     contribs.append(_contrib("<stat>", <const>[t], "<text>", "<Pick A>"))

    # ── <Pick B> (unlock 60, slot 2) ────────────────────────────────────────────
    # ── <Pick C> (unlock 75, slot 3) ────────────────────────────────────────────

    return {"contributions": contribs}


def stash(*, source, ls_state, inflict_aps):
    """Capture converged scalars next pass's apply() needs (block ratio, movement speed, etc.). Omit if unused."""
    # ls_state["<scalar>"] = source.total("<stat>")
    pass


def status_lines(*, slot_levels, advanced_picks):
    """One status row per trait line so every line is surfaced (never silently dropped)."""
    picks = set(advanced_picks or [])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    # working("<base line>", "<Trait Name>")
    # info("<spatial/regen line not computed>", "<Trait Name>")
    # if "<Pick A>" in picks: working("<pick A line>", "<Pick A>")
    return out
