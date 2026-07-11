"""Tests for `tools/season_impact.py` — component F of the season-diff system.

Everything here is SYNTHETIC: hand-built diff-artifact dicts matching the shape produced by the
sibling crawler repo's `tools.season_diff` package (see that repo's `skill_diff.py`/`gear_diff.py`/
`line_pool.py`/`engine.py` for the authoritative shape this mirrors), never a dependency on the
crawler repo's real `output/` directory existing. Anything `season_impact.py` reads from real repo
state (the local season catalog via `persistence.season_manager`, `engine.skill_resolver._REGISTRY`,
`data/verification/`, `backend/tests/fixtures/`) is monkeypatched to a tiny fixture so tests are
hermetic and don't depend on which season happens to be imported on this machine.

This module owns no production source — `backend/tools/season_impact.py` is out of scope for
edits here; any real defect found gets logged to `.wolf/buglog.json` and reported, not patched.
"""
import json

import pytest

import tools.season_impact as season_impact


# ── _load_catalog_maps ────────────────────────────────────────────────────────────────────────

def _fake_season_manager(monkeypatch, data: dict[str, tuple[dict | None, dict | None]]):
    """Patch `season_impact.season_manager` to serve `{season: (skills_data, gear_data)}` from
    `data`, with `list_seasons()` reporting exactly the seasons present as keys."""
    monkeypatch.setattr(season_impact.season_manager, "list_seasons", lambda: list(data.keys()))
    monkeypatch.setattr(
        season_impact.season_manager, "load_skills",
        lambda season, raw=False: data.get(season, (None, None))[0],
    )
    monkeypatch.setattr(
        season_impact.season_manager, "load_legendary_gear",
        lambda season: data.get(season, (None, None))[1],
    )


_SKILLS_A = {"skills": [{"uuid": "u-a", "item_id": "item_a", "name": "Skill A", "skill_type": "active_skill"}]}
_GEAR_A = {"items": [{"uuid": "g-a", "item_id": "gear_a", "name": "Gear A"}]}
_SKILLS_B = {"skills": [{"uuid": "u-b", "item_id": "item_b", "name": "Skill B", "skill_type": "support_skill"}]}
_GEAR_B = {"items": [{"uuid": "g-b", "item_id": "gear_b", "name": "Gear B"}]}


def test_load_catalog_maps_prefers_season_b(monkeypatch):
    _fake_season_manager(monkeypatch, {
        "SS11": (_SKILLS_A, _GEAR_A),
        "SS12": (_SKILLS_B, _GEAR_B),
    })
    skills_map, gear_map, used = season_impact._load_catalog_maps("SS11", "SS12")
    assert used == "SS12"
    assert set(skills_map.keys()) == {"u-b"}
    assert skills_map["u-b"]["item_id"] == "item_b"
    assert set(gear_map.keys()) == {"g-b"}


def test_load_catalog_maps_falls_back_to_season_a_when_b_not_on_disk(monkeypatch):
    _fake_season_manager(monkeypatch, {
        "SS11": (_SKILLS_A, _GEAR_A),
        # SS12 not present at all — not an available season.
    })
    skills_map, gear_map, used = season_impact._load_catalog_maps("SS11", "SS12")
    assert used == "SS11"
    assert set(skills_map.keys()) == {"u-a"}


def test_load_catalog_maps_falls_back_when_season_b_data_is_empty(monkeypatch):
    # SS12 IS an available season dir, but has neither skills nor gear data on disk (both None) —
    # must still fall through to season_a rather than returning an empty result early.
    _fake_season_manager(monkeypatch, {
        "SS11": (_SKILLS_A, _GEAR_A),
        "SS12": (None, None),
    })
    skills_map, gear_map, used = season_impact._load_catalog_maps("SS11", "SS12")
    assert used == "SS11"
    assert set(skills_map.keys()) == {"u-a"}


def test_load_catalog_maps_both_missing_returns_empty_no_crash(monkeypatch):
    _fake_season_manager(monkeypatch, {})
    skills_map, gear_map, used = season_impact._load_catalog_maps("SS11", "SS12")
    assert skills_map == {}
    assert gear_map == {}
    assert used is None


# ── _registry_scoped_skill_types ──────────────────────────────────────────────────────────────

def test_registry_scoped_skill_types_derives_only_types_with_a_registry_hit(monkeypatch):
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"foo_active": lambda: None})
    skills_uuid_map = {
        "u1": {"item_id": "foo_active", "name": "Foo", "skill_type": "active_skill"},
        "u2": {"item_id": "bar_support", "name": "Bar", "skill_type": "support_skill"},
        "u3": {"item_id": None, "name": "Baz", "skill_type": "passive_skill"},
    }
    assert season_impact._registry_scoped_skill_types(skills_uuid_map) == {"active_skill"}


def test_registry_scoped_skill_types_empty_registry_yields_empty_set(monkeypatch):
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {})
    skills_uuid_map = {
        "u1": {"item_id": "foo_active", "name": "Foo", "skill_type": "active_skill"},
    }
    assert season_impact._registry_scoped_skill_types(skills_uuid_map) == set()


# ── _classify_type ─────────────────────────────────────────────────────────────────────────────

def test_classify_type_sniffs_gear_via_variants_key():
    type_block = {"entities": {"u1": {"variants": [], "verdict": "reworked"}}}
    assert season_impact._classify_type("some_new_gear_type", type_block) == "gear"


def test_classify_type_sniffs_skill_via_line_changes_key():
    type_block = {"entities": {"u1": {"line_changes": {}, "verdict": "renumbered"}}}
    assert season_impact._classify_type("some_new_skill_type", type_block) == "skill"


def test_classify_type_falls_back_to_known_gear_type_name_when_entities_are_stubs():
    # engine.py's added/removed entries are bare {verdict, name_before, name_after} stubs — no
    # variants/line_changes key to sniff — so classification must fall back to the type name.
    type_block = {"entities": {"u1": {"verdict": "added", "name_before": None, "name_after": "New Thing"}}}
    assert season_impact._classify_type("legendary_gear", type_block) == "gear"


def test_classify_type_falls_back_to_known_skill_type_name_when_entities_are_stubs():
    type_block = {"entities": {"u1": {"verdict": "removed", "name_before": "Old Thing", "name_after": None}}}
    assert season_impact._classify_type("active_skill", type_block) == "skill"


def test_classify_type_unknown_when_shape_and_name_both_unrecognized():
    type_block = {"entities": {"u1": {"verdict": "added", "name_before": None, "name_after": "Widget"}}}
    assert season_impact._classify_type("widget_shape", type_block) == "unknown"


def test_classify_type_unknown_with_no_entities_at_all():
    assert season_impact._classify_type("widget_shape", {"entities": {}}) == "unknown"


# ── _collect_new_wording ──────────────────────────────────────────────────────────────────────

def _line_changes(**overrides) -> dict:
    base = {
        "added": [], "removed": [], "renumbered": [], "cosmetic": [],
        "template_changed": [], "localization_mismatch": [], "regrouped": [],
        "unchanged_count": 0,
    }
    base.update(overrides)
    return base


def test_collect_new_wording_includes_added_and_template_changed_only():
    entity = {
        "variants": [
            {
                "rarity_state": "corroded",
                "status": "compared",
                "line_changes": _line_changes(
                    added=[{"modifier_id": "m1", "pooling_uuid": "p1", "text": "New affix line here"}],
                    renumbered=[{
                        "pooling_uuid": "p2", "modifier_id": "m2",
                        "text_before": "+10% Increased Fire Damage", "text_after": "+15% Increased Fire Damage",
                        "numeric_delta": [{"delta": 5}],
                    }],
                    cosmetic=[{
                        "pooling_uuid": "p3", "modifier_id": "m3",
                        "text_before": "Deals damage", "text_after": "Deals damage.",
                    }],
                    template_changed=[{
                        "modifier_id": "m4", "pooling_uuid_before": "p4", "pooling_uuid_after": "p5",
                        "text_before": "Old wording entirely", "text_after": "Brand new wording entirely",
                    }],
                    regrouped=[{"removed": [{"text": "split a"}], "added": [{"text": "split b"}]}],
                ),
            },
            # No line_changes at all on a non-"compared" variant — must be skipped, not KeyError.
            {"rarity_state": "base", "status": "variant_added"},
        ],
        "random_affixes": [
            {
                "rarity_state": "corroded", "placeholder": "P1", "status": "compared",
                "line_changes": _line_changes(
                    added=[{"modifier_id": "ra1", "text": "Random affix new text"}],
                ),
            },
            {"rarity_state": "corroded", "placeholder": "P2", "status": "slot_added"},
        ],
    }

    result = season_impact._collect_new_wording(entity)

    assert len(result) == 3
    kinds = {(r["source"], r["kind"], r["text"]) for r in result}
    assert kinds == {
        ("variant:corroded", "added", "New affix line here"),
        ("variant:corroded", "template_changed", "Brand new wording entirely"),
        ("random_affix:corroded/P1", "added", "Random affix new text"),
    }

    texts = [r["text"] for r in result]
    # Explicitly assert the excluded categories' wording never leaks through.
    assert "+15% Increased Fire Damage" not in texts   # renumbered
    assert "Deals damage." not in texts                 # cosmetic
    assert "split b" not in texts                        # regrouped
    assert "Old wording entirely" not in texts            # template_changed's BEFORE text, not after


def test_collect_new_wording_empty_entity_yields_empty_list():
    assert season_impact._collect_new_wording({}) == []


def test_collect_new_wording_pure_renumber_only_yields_nothing():
    entity = {
        "variants": [{
            "rarity_state": "base", "status": "compared",
            "line_changes": _line_changes(
                renumbered=[{
                    "pooling_uuid": "p1", "modifier_id": "m1",
                    "text_before": "+10% Increased Cold Damage", "text_after": "+20% Increased Cold Damage",
                    "numeric_delta": [{"delta": 10}],
                }],
            ),
        }],
    }
    assert season_impact._collect_new_wording(entity) == []


def test_collect_new_wording_pure_cosmetic_only_yields_nothing():
    entity = {
        "variants": [{
            "rarity_state": "base", "status": "compared",
            "line_changes": _line_changes(
                cosmetic=[{"pooling_uuid": "p1", "modifier_id": "m1", "text_before": "Hi", "text_after": "Hi."}],
            ),
        }],
    }
    assert season_impact._collect_new_wording(entity) == []


def test_collect_new_wording_pure_regroup_only_yields_nothing():
    entity = {
        "variants": [{
            "rarity_state": "base", "status": "compared",
            "line_changes": _line_changes(
                regrouped=[{"removed": [{"text": "a b"}], "added": [{"text": "a"}, {"text": "b"}]}],
            ),
        }],
    }
    assert season_impact._collect_new_wording(entity) == []


# ── _matching_golden_files ────────────────────────────────────────────────────────────────────

_FIXTURE_INDEX = {
    "tests/fixtures/support_skill_golden/path_of_flames.json": json.dumps(
        {"item_id": "other_id", "name": "Something Else"}
    ),
    "tests/fixtures/composite_baseline.json": json.dumps(
        {"foo": "bar", "item_id": "target_item"}
    ),
    "tests/fixtures/name_substring_fixture.json": json.dumps(
        {"description": "Mentions Blazing Storm somewhere in this text"}
    ),
    "tests/fixtures/unrelated.json": json.dumps({"nothing": "to see here"}),
}


def test_matching_golden_files_filename_slug_match():
    hits = season_impact._matching_golden_files(_FIXTURE_INDEX, None, "Path Of Flames", "Path Of Flames")
    assert "tests/fixtures/support_skill_golden/path_of_flames.json" in hits


def test_matching_golden_files_item_id_substring_match():
    hits = season_impact._matching_golden_files(
        _FIXTURE_INDEX, "target_item", "Something Unrelated Name", "Something Unrelated Name"
    )
    assert "tests/fixtures/composite_baseline.json" in hits
    # And it must NOT also match on filename-slug or name-substring for this item.
    assert "tests/fixtures/support_skill_golden/path_of_flames.json" not in hits


def test_matching_golden_files_name_substring_match():
    hits = season_impact._matching_golden_files(_FIXTURE_INDEX, None, "Blazing Storm", "Blazing Storm")
    assert "tests/fixtures/name_substring_fixture.json" in hits


def test_matching_golden_files_no_match_returns_empty():
    hits = season_impact._matching_golden_files(_FIXTURE_INDEX, "nope_id", "Nothing Matches Here At All", "Nothing Matches Here At All")
    assert hits == []


# ── _skill_impact — the registry-scope gate (headline design nuance) ────────────────────────────

def test_skill_impact_support_skill_is_never_flagged_not_modeled(monkeypatch):
    """A changed SUPPORT skill must not be misreported as 'not modeled' just because it has no
    skill_resolver._REGISTRY entry — supports are modeled generically by support_resolver.py /
    support_lines.py, so has_registry_entry is deliberately not computed for it at all."""
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": lambda: None})
    skills_uuid_map = {
        "uuid-support": {"item_id": "path_of_flames", "name": "Path of Flames", "skill_type": "support_skill"},
    }
    registry_scoped_types = {"active_skill"}  # empirically derived; support_skill is NOT in it
    entity = {
        "verdict": "reworked", "name_before": "Path of Flames", "name_after": "Path of Flames",
        "line_changes": {}, "scalar_changes": {},
    }
    result = season_impact._skill_impact(
        "support_skill", "uuid-support", entity, skills_uuid_map, registry_scoped_types, {}, {},
    )
    assert result["registry_applicable"] is False
    assert result["has_registry_entry"] is None
    assert result["resolution"] == "not_registry_scoped"
    assert result["registry_module"] is None
    assert result["registry_function"] is None


def test_skill_impact_passive_skill_is_never_flagged_not_modeled(monkeypatch):
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {})
    skills_uuid_map = {
        "uuid-passive": {"item_id": "some_passive", "name": "Some Passive", "skill_type": "passive_skill"},
    }
    registry_scoped_types = {"active_skill"}
    entity = {
        "verdict": "renumbered", "name_before": "Some Passive", "name_after": "Some Passive",
        "line_changes": {}, "scalar_changes": {},
    }
    result = season_impact._skill_impact(
        "passive_skill", "uuid-passive", entity, skills_uuid_map, registry_scoped_types, {}, {},
    )
    assert result["registry_applicable"] is False
    assert result["has_registry_entry"] is None
    assert result["resolution"] == "not_registry_scoped"


def test_skill_impact_active_skill_with_registry_entry_is_modeled(monkeypatch):
    fn = lambda: None  # noqa: E731
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": fn})
    skills_uuid_map = {
        "uuid-a": {"item_id": "chain_lightning", "name": "Chain Lightning", "skill_type": "active_skill"},
    }
    registry_scoped_types = {"active_skill"}
    entity = {
        "verdict": "renumbered", "name_before": "Chain Lightning", "name_after": "Chain Lightning",
        "line_changes": {}, "scalar_changes": {},
    }
    result = season_impact._skill_impact(
        "active_skill", "uuid-a", entity, skills_uuid_map, registry_scoped_types, {}, {},
    )
    assert result["registry_applicable"] is True
    assert result["has_registry_entry"] is True
    assert result["resolution"] == "resolved"
    assert result["registry_module"] == fn.__module__
    assert result["registry_function"] == fn.__qualname__


def test_skill_impact_active_skill_without_registry_entry_is_not_modeled(monkeypatch):
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {})
    skills_uuid_map = {
        "uuid-b": {"item_id": "new_active_skill", "name": "New Active Skill", "skill_type": "active_skill"},
    }
    registry_scoped_types = {"active_skill"}
    entity = {
        "verdict": "reworked", "name_before": "New Active Skill", "name_after": "New Active Skill",
        "line_changes": {}, "scalar_changes": {},
    }
    result = season_impact._skill_impact(
        "active_skill", "uuid-b", entity, skills_uuid_map, registry_scoped_types, {}, {},
    )
    assert result["registry_applicable"] is True
    assert result["has_registry_entry"] is False
    assert result["resolution"] == "resolved"


def test_skill_impact_registry_scoped_type_but_no_catalog_entry_is_unresolved(monkeypatch):
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": lambda: None})
    registry_scoped_types = {"active_skill"}
    entity = {
        "verdict": "renumbered", "name_before": "Mystery Skill", "name_after": "Mystery Skill",
        "line_changes": {}, "scalar_changes": {},
    }
    result = season_impact._skill_impact(
        "active_skill", "uuid-unknown", entity, {}, registry_scoped_types, {}, {},
    )
    assert result["registry_applicable"] is True
    assert result["has_registry_entry"] is None
    assert result["resolution"] == "unresolved_no_catalog_entry"


# ── _gear_impact ───────────────────────────────────────────────────────────────────────────────

def test_gear_impact_flags_unresolved_new_affix_text():
    entity = {
        "verdict": "reworked", "name_before": "Test Ring", "name_after": "Test Ring",
        "variants": [{
            "rarity_state": "corroded", "status": "compared",
            "line_changes": _line_changes(
                added=[{"modifier_id": "m1", "text": "totally new resolvable text"}],
                template_changed=[{"modifier_id": "m2", "text_before": "old", "text_after": "totally new unresolvable text"}],
            ),
        }],
        "random_affixes": [],
    }

    def fake_resolve(text: str) -> bool:
        return "resolvable" in text and "unresolvable" not in text

    result = season_impact._gear_impact(
        "uuid-gear", entity, {"uuid-gear": {"item_id": "test_ring", "name": "Test Ring"}}, fake_resolve,
    )
    assert result["item_id"] == "test_ring"
    assert len(result["new_affix_texts"]) == 2
    assert len(result["new_affix_unresolved"]) == 1
    assert result["new_affix_unresolved"][0]["text"] == "totally new unresolvable text"


def test_gear_impact_pure_renumber_has_no_new_affix_text():
    entity = {
        "verdict": "renumbered", "name_before": "Test Amulet", "name_after": "Test Amulet",
        "variants": [{
            "rarity_state": "base", "status": "compared",
            "line_changes": _line_changes(
                renumbered=[{"pooling_uuid": "p1", "modifier_id": "m1", "text_before": "+10%", "text_after": "+20%", "numeric_delta": []}],
            ),
        }],
        "random_affixes": [],
    }
    result = season_impact._gear_impact("uuid-g2", entity, {}, lambda text: True)
    assert result["new_affix_texts"] == []
    assert result["new_affix_unresolved"] == []


# ── run_impact — end-to-end wiring, including the registry-scope gate at the summary level ──────

def _write_diff_artifact(tmp_path, season_a: str, season_b: str, types: dict) -> str:
    diff = {"season_a": season_a, "season_b": season_b, "generated_at": "2026-07-11T00:00:00+00:00", "types": types}
    path = tmp_path / f"season-diff-{season_a}-{season_b}.json"
    path.write_text(json.dumps(diff), encoding="utf-8")
    return str(path)


@pytest.fixture
def impact_env(tmp_path, monkeypatch):
    """A fully hermetic environment for `run_impact`: fake season catalog, fake registry, fake
    verification dir, fake fixtures dir — no dependency on real `data/` or `backend/tests/`
    contents beyond what this fixture writes."""
    skills_data = {
        "skills": [
            {"uuid": "u-modeled", "item_id": "chain_lightning", "name": "Chain Lightning", "skill_type": "active_skill"},
            {"uuid": "u-unmodeled", "item_id": "new_active_skill", "name": "New Active Skill", "skill_type": "active_skill"},
            {"uuid": "u-support", "item_id": "path_of_flames", "name": "Path of Flames", "skill_type": "support_skill"},
        ]
    }
    gear_data = {"items": [{"uuid": "u-gear", "item_id": "test_ring", "name": "Test Ring"}]}
    _fake_season_manager(monkeypatch, {"SS12": (skills_data, gear_data)})
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": lambda: None})

    verification_dir = tmp_path / "verification"
    verification_dir.mkdir()
    (verification_dir / "chain-lightning.json").write_text(
        json.dumps({"id": "chain-lightning", "skills": ["Chain Lightning"]}), encoding="utf-8"
    )
    monkeypatch.setattr(season_impact, "_VERIFICATION_DIR", str(verification_dir))

    fixtures_dir = tmp_path / "fixtures"
    (fixtures_dir / "sub").mkdir(parents=True)
    (fixtures_dir / "sub" / "chain_lightning.json").write_text(
        json.dumps({"item_id": "chain_lightning", "total_dps": 123.0}), encoding="utf-8"
    )
    monkeypatch.setattr(season_impact, "_FIXTURES_DIR", str(fixtures_dir))

    return tmp_path


def test_run_impact_registry_gate_and_summary_counts(impact_env, monkeypatch):
    types = {
        "active_skill": {
            "counts": {}, "entities": {
                "u-modeled": {
                    "verdict": "renumbered", "name_before": "Chain Lightning", "name_after": "Chain Lightning",
                    "line_changes": _line_changes(), "scalar_changes": {"mana_cost": {"before": 10, "after": 12}},
                },
                "u-unmodeled": {
                    "verdict": "reworked", "name_before": "New Active Skill", "name_after": "New Active Skill",
                    "line_changes": _line_changes(added=[{"modifier_id": "x", "text": "new line"}]), "scalar_changes": {},
                },
                "u-unknown-catalog": {
                    "verdict": "renumbered", "name_before": "Mystery Skill", "name_after": "Mystery Skill",
                    "line_changes": _line_changes(), "scalar_changes": {},
                },
            },
        },
        "support_skill": {
            "counts": {}, "entities": {
                "u-support": {
                    "verdict": "reworked", "name_before": "Path of Flames", "name_after": "Path of Flames",
                    "line_changes": _line_changes(added=[{"modifier_id": "y", "text": "new support line"}]), "scalar_changes": {},
                },
            },
        },
        "legendary_gear": {
            "counts": {}, "entities": {
                "u-gear": {
                    "verdict": "reworked", "name_before": "Test Ring", "name_after": "Test Ring",
                    "variants": [{
                        "rarity_state": "corroded", "status": "compared",
                        "line_changes": _line_changes(
                            added=[{"modifier_id": "g1", "text": "+20% Increased Fire Damage"}],
                            template_changed=[{
                                "modifier_id": "g2", "text_before": "old wording",
                                "text_after": "totally unresolvable made up affix xyzzy 12345",
                            }],
                        ),
                    }],
                    "random_affixes": [],
                },
            },
        },
        "activation_medium_skill": {
            "no_historical_baseline": True, "present_in": "B", "entity_count": 5,
        },
        "widget_shape": {
            "counts": {}, "entities": {
                "u-widget": {"verdict": "added", "name_before": None, "name_after": "New Widget"},
            },
        },
    }
    diff_path = _write_diff_artifact(impact_env, "SS11", "SS12", types)

    report = season_impact.run_impact(diff_path)
    s = report["summary"]

    assert report["catalog_season_used"] == "SS12"

    # Headline scope gate: the changed SUPPORT skill is never counted toward "not modeled".
    assert s["changed_skills_registry_scoped_types"] == ["active_skill"]
    assert s["changed_skills_not_registry_scoped"] == 1
    support_entry = next(x for x in report["skills"] if x["uuid"] == "u-support")
    assert support_entry["registry_applicable"] is False
    assert support_entry["has_registry_entry"] is None
    assert support_entry["resolution"] == "not_registry_scoped"

    # Registry-scoped active_skill verdicts.
    assert s["changed_skills_total"] == 4
    assert s["changed_skills_modeled"] == 1
    assert s["changed_skills_not_modeled"] == 1
    assert s["changed_skills_unresolved_no_catalog"] == 1
    assert s["changed_skills_removed"] == 0

    modeled_entry = next(x for x in report["skills"] if x["uuid"] == "u-modeled")
    assert modeled_entry["has_registry_entry"] is True
    assert modeled_entry["item_id"] == "chain_lightning"
    assert "chain-lightning" in modeled_entry["verification_ids"]
    assert any("chain_lightning" in g for g in modeled_entry["golden_files"])

    unmodeled_entry = next(x for x in report["skills"] if x["uuid"] == "u-unmodeled")
    assert unmodeled_entry["has_registry_entry"] is False
    assert unmodeled_entry["resolution"] == "resolved"

    unknown_catalog_entry = next(x for x in report["skills"] if x["uuid"] == "u-unknown-catalog")
    assert unknown_catalog_entry["resolution"] == "unresolved_no_catalog_entry"
    assert unknown_catalog_entry["has_registry_entry"] is None

    # Gear: one changed item, new affix text present, one of the two new lines unresolved.
    assert s["changed_gear_total"] == 1
    assert s["changed_gear_with_new_affix_text"] == 1
    assert s["changed_gear_new_affix_unresolved"] == 1
    gear_entry = report["gear"][0]
    assert gear_entry["item_id"] == "test_ring"
    assert len(gear_entry["new_affix_texts"]) == 2
    assert len(gear_entry["new_affix_unresolved"]) == 1
    assert "xyzzy" in gear_entry["new_affix_unresolved"][0]["text"]

    # Unknown-shaped type and no-baseline type are surfaced, not silently dropped or miscounted.
    assert s["types_skipped_unknown_shape"] == ["widget_shape"]
    assert "activation_medium_skill" in s["types_with_no_historical_baseline"]
    assert s["types_with_no_historical_baseline"]["activation_medium_skill"]["entity_count"] == 5


def test_run_impact_markdown_renders_without_crashing(impact_env):
    types = {
        "active_skill": {
            "counts": {}, "entities": {
                "u-modeled": {
                    "verdict": "renumbered", "name_before": "Chain Lightning", "name_after": "Chain Lightning",
                    "line_changes": _line_changes(), "scalar_changes": {},
                },
            },
        },
    }
    diff_path = _write_diff_artifact(impact_env, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)
    md = season_impact.render_markdown(report)
    assert "SS11 -> SS12" in md
    assert "Chain Lightning" in md


# ── FIX 1 — a catalog entry with no skill_type must not enter registry_scoped_types ─────────────
# (a bare None sorted against str previously blew up `sorted(registry_scoped_types)` in both the
# summary dict and render_markdown's "in a REGISTRY-scoped type (...)" sentence.)

def test_registry_scoped_skill_types_skips_entry_with_missing_skill_type(monkeypatch):
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"foo_active": lambda: None})
    skills_uuid_map = {
        "u1": {"item_id": "foo_active", "name": "Foo", "skill_type": None},
    }
    result = season_impact._registry_scoped_skill_types(skills_uuid_map)
    assert result == set()
    sorted(result)  # must not raise even though this entry contributed nothing


def test_registry_scoped_skill_types_none_skill_type_mixed_with_valid_does_not_crash_sorted(monkeypatch):
    monkeypatch.setattr(
        season_impact, "SKILL_REGISTRY", {"foo_active": lambda: None, "bar_active": lambda: None}
    )
    skills_uuid_map = {
        "u1": {"item_id": "foo_active", "name": "Foo", "skill_type": None},
        "u2": {"item_id": "bar_active", "name": "Bar", "skill_type": "active_skill"},
    }
    result = season_impact._registry_scoped_skill_types(skills_uuid_map)
    assert result == {"active_skill"}
    assert sorted(result) == ["active_skill"]  # would raise TypeError('<' NoneType vs str) pre-fix


def test_run_impact_handles_catalog_entry_with_missing_skill_type(tmp_path, monkeypatch):
    """Regression exercised end-to-end: a catalog entry whose item_id IS in SKILL_REGISTRY but
    skill_type is missing/None must not blow up the later sorted(registry_scoped_types) call
    inside run_impact's summary construction or render_markdown."""
    skills_data = {
        "skills": [
            {"uuid": "u-no-type", "item_id": "chain_lightning", "name": "Chain Lightning", "skill_type": None},
        ]
    }
    _fake_season_manager(monkeypatch, {"SS12": (skills_data, None)})
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": lambda: None})
    monkeypatch.setattr(season_impact, "_VERIFICATION_DIR", str(tmp_path / "no-such-verification-dir"))
    monkeypatch.setattr(season_impact, "_FIXTURES_DIR", str(tmp_path / "no-such-fixtures-dir"))

    types = {
        "active_skill": {
            "counts": {}, "entities": {
                "u-no-type": {
                    "verdict": "renumbered", "name_before": "Chain Lightning", "name_after": "Chain Lightning",
                    "line_changes": _line_changes(), "scalar_changes": {},
                },
            },
        },
    }
    diff_path = _write_diff_artifact(tmp_path, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)  # must not raise
    assert report["summary"]["changed_skills_registry_scoped_types"] == []

    md = season_impact.render_markdown(report)  # must not raise TypeError from sorted(None, str)
    assert "SS11 -> SS12" in md


# ── FIX 2 (HIGH) — missing local catalog must bucket as unresolved, never falsely "not modeled" ─

def test_run_impact_catalog_missing_buckets_unresolved_not_falsely_not_modeled(tmp_path, monkeypatch):
    _fake_season_manager(monkeypatch, {})  # neither season on disk anywhere
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": lambda: None})
    monkeypatch.setattr(season_impact, "_VERIFICATION_DIR", str(tmp_path / "no-verification"))
    monkeypatch.setattr(season_impact, "_FIXTURES_DIR", str(tmp_path / "no-fixtures"))

    types = {
        "active_skill": {
            "counts": {}, "entities": {
                "u-cl": {
                    "verdict": "renumbered", "name_before": "Chain Lightning", "name_after": "Chain Lightning",
                    "line_changes": _line_changes(), "scalar_changes": {},
                },
            },
        },
    }
    diff_path = _write_diff_artifact(tmp_path, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)
    s = report["summary"]

    assert report["catalog_season_used"] is None
    assert s["catalog_missing"] is True
    assert s["changed_skills_unresolved_catalog_missing"] == 1
    # Must NOT be misclassified into either of the two buckets a real bug flipped this into.
    assert s["changed_skills_not_modeled"] == 0
    assert s["changed_skills_not_registry_scoped"] == 0

    entry = next(x for x in report["skills"] if x["uuid"] == "u-cl")
    assert entry["resolution"] == "unresolved_no_catalog"
    assert entry["resolution"] != "not_registry_scoped"
    assert entry["resolution"] != "resolved"
    assert entry["has_registry_entry"] is None

    md = season_impact.render_markdown(report)
    assert "WARNING: season catalog not on disk" in md


# ── FIX 3 — localization-mismatch-only entities surface in their own bucket, not the normal ones ─

def test_run_impact_surfaces_localization_mismatch_only_entities(impact_env):
    types = {
        "active_skill": {
            "counts": {}, "entities": {
                "u-locmis": {
                    "verdict": "unchanged", "name_before": "Weird Skill", "name_after": "Weird Skill",
                    "has_localization_mismatch": True,
                },
                "u-plain-unchanged": {
                    "verdict": "unchanged", "name_before": "Boring Skill", "name_after": "Boring Skill",
                },
            },
        },
    }
    diff_path = _write_diff_artifact(impact_env, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)
    s = report["summary"]

    assert s["localization_mismatch_entities_total"] == 1
    loc = report["localization_mismatches"][0]
    assert loc["name"] == "Weird Skill"
    assert loc["uuid"] == "u-locmis"

    # Not run through the normal modeled/not-modeled skill buckets at all.
    assert all(sk["uuid"] != "u-locmis" for sk in report["skills"])
    # A plain unchanged entity WITHOUT the mismatch flag is dropped, not surfaced anywhere.
    assert all(sk["uuid"] != "u-plain-unchanged" for sk in report["skills"])
    assert all(x["uuid"] != "u-plain-unchanged" for x in report["localization_mismatches"])

    md = season_impact.render_markdown(report)
    assert "Localization mismatch" in md
    assert "needs re-crawl" in md
    assert "Weird Skill" in md


# ── FIX 4 — entity types outside skill/gear scope with an unrecognized shape render, not vanish ──

def test_run_impact_unknown_shape_type_recorded_and_rendered(impact_env):
    types = {
        "hero_trait": {
            "counts": {}, "entities": {
                "u-trait": {"verdict": "reworked", "name_before": "Old Trait", "name_after": "New Trait"},
            },
        },
    }
    diff_path = _write_diff_artifact(impact_env, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)
    s = report["summary"]

    assert s["types_skipped_unknown_shape"] == ["hero_trait"]
    assert report["skills"] == []
    assert report["gear"] == []

    md = season_impact.render_markdown(report)
    assert "Not analyzed by this tool (unrecognized entity shape)" in md
    assert "hero_trait" in md


# ── FIX 5 — golden-name matching is a whole-name (word-boundary) match, not raw substring ────────

_WORD_BOUNDARY_FIXTURE_INDEX = {
    "tests/fixtures/firestorm_fixture.json": json.dumps(
        {"description": "This mentions Firestorm Totem in passing"}
    ),
    "tests/fixtures/storm_whole_word_fixture.json": json.dumps(
        {"description": "The Storm ability now scales differently"}
    ),
}


def test_matching_golden_files_word_boundary_rejects_substring_match():
    hits = season_impact._matching_golden_files(_WORD_BOUNDARY_FIXTURE_INDEX, None, "Storm", "Storm")
    assert "tests/fixtures/firestorm_fixture.json" not in hits
    assert "tests/fixtures/storm_whole_word_fixture.json" in hits


def test_name_word_boundary_match_directly():
    assert season_impact._name_word_boundary_match("Storm", "Firestorm Totem deals damage") is False
    assert season_impact._name_word_boundary_match("Storm", "The Storm ability") is True
    assert season_impact._name_word_boundary_match("Storm", "Storm-touched gear") is True
    assert season_impact._name_word_boundary_match("", "anything") is False


# ── verdict="removed" through the impact layer (orthogonal removed + modeled/not-modeled) ────────

def test_skill_impact_removed_stub_shape_does_not_crash_and_still_resolves(monkeypatch):
    """engine.py's `removed` entries are bare {verdict, name_before, name_after} stubs — no
    line_changes/variants/scalar_changes key at all — _skill_impact must not KeyError on them,
    and a registry-modeled removed skill must still resolve (removed-ness is orthogonal to the
    modeled/not-modeled verdict, not a separate bucket that suppresses it)."""
    monkeypatch.setattr(season_impact, "SKILL_REGISTRY", {"chain_lightning": lambda: None})
    skills_uuid_map = {
        "uuid-removed": {"item_id": "chain_lightning", "name": "Chain Lightning", "skill_type": "active_skill"},
    }
    registry_scoped_types = {"active_skill"}
    entity = {"verdict": "removed", "name_before": "Chain Lightning", "name_after": None}
    result = season_impact._skill_impact(
        "active_skill", "uuid-removed", entity, skills_uuid_map, registry_scoped_types, {}, {},
    )
    assert result["verdict"] == "removed"
    assert result["has_registry_entry"] is True
    assert result["resolution"] == "resolved"
    assert result["name"] == "Chain Lightning"
    assert result["name_before"] is None  # name_after fell back to name_before, so they're equal
    assert result["line_change_counts"] == {}


def test_run_impact_removed_active_skill_counted_orthogonally_in_removed_and_modeled(impact_env):
    types = {
        "active_skill": {
            "counts": {}, "entities": {
                "u-modeled": {
                    "verdict": "removed", "name_before": "Chain Lightning", "name_after": None,
                },
            },
        },
    }
    diff_path = _write_diff_artifact(impact_env, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)
    s = report["summary"]

    # Orthogonal design: a removed skill that's ALSO registry-modeled counts in both buckets.
    assert s["changed_skills_removed"] == 1
    assert s["changed_skills_modeled"] == 1

    entry = report["skills"][0]
    assert entry["verdict"] == "removed"
    assert entry["has_registry_entry"] is True
    assert entry["name"] == "Chain Lightning"

    md = season_impact.render_markdown(report)  # must not crash on the stub shape
    assert "Chain Lightning" in md


def test_gear_impact_removed_stub_shape_does_not_crash():
    entity = {"verdict": "removed", "name_before": "Old Ring", "name_after": None}
    result = season_impact._gear_impact("uuid-g", entity, {}, lambda text: True)
    assert result["name"] == "Old Ring"
    assert result["variants_added"] == 0
    assert result["variants_removed"] == 0
    assert result["new_affix_texts"] == []
    assert result["new_affix_unresolved"] == []


def test_run_impact_gear_removed_and_added_stubs_do_not_crash(impact_env):
    types = {
        "legendary_gear": {
            "counts": {}, "entities": {
                "u-gear-removed": {
                    "verdict": "removed", "name_before": "Old Ring", "name_after": None,
                },
                "u-gear-added": {
                    "verdict": "added", "name_before": None, "name_after": "New Ring",
                },
            },
        },
    }
    diff_path = _write_diff_artifact(impact_env, "SS11", "SS12", types)
    report = season_impact.run_impact(diff_path)
    s = report["summary"]

    assert s["changed_gear_total"] == 2
    names = {g["name"] for g in report["gear"]}
    assert names == {"Old Ring", "New Ring"}
    for g in report["gear"]:
        assert g["new_affix_texts"] == []
        assert g["new_affix_unresolved"] == []

    md = season_impact.render_markdown(report)  # must not crash on stub shapes
    assert "Old Ring" in md
    assert "New Ring" in md
