"""
_COND_PATTERNS: "(haven't/have not) been hit recently" vs "have been hit recently" / "hit recently".
Council-requested pin: the negated phrasing CONTAINS the substring "hit recently", so if the negated
entry in _COND_PATTERNS ever stops being checked before the positive entry (ordering flip, refactor
that breaks first-match-wins), "haven't been hit recently" would silently resolve to the positive
{"not": ...} key instead. These tests pin both directions plus a neighbor condition
(recently_taken_damage) that must not get cross-captured by the new patterns.
"""
from server import _translate_condition_expr as T


def test_negated_havent_been_hit_recently():
    expr = T("+30% Movement Speed if you haven't been hit recently")
    assert expr == {"not": "recently_hit"}


def test_negated_have_not_been_hit_recently():
    expr = T("Grants a bonus if you have not been hit recently")
    assert expr == {"not": "recently_hit"}


def test_positive_have_been_hit_recently():
    expr = T("Deals bonus damage if you have been hit recently")
    assert expr == "recently_hit"


def test_positive_bare_hit_recently():
    expr = T("+10% Damage if hit recently")
    assert expr == "recently_hit"


def test_recently_taken_damage_not_cross_captured():
    # A distinct condition key ("recently_taken_damage") sharing the word "recently" must still
    # resolve to its own key, not to recently_hit, and vice versa the recently_hit patterns must not
    # match "taken damage" phrasing.
    assert T("+15% Life Regeneration if you have taken damage in the last 3s") == "recently_taken_damage"
    assert T("Grants a buff if you have recently taken damage") == "recently_taken_damage"


def test_recently_hit_patterns_do_not_match_taken_damage_phrasing():
    expr = T("+15% Life Regeneration if you have taken damage in the last 3s")
    assert expr != "recently_hit"
    assert expr != {"not": "recently_hit"}
