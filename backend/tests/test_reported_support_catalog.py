"""Reported support pairings remain intact through the real catalog endpoint."""
import pytest

from persistence import season_manager
from server import get_skills


@pytest.mark.parametrize('season', ['SS12', 'SS13'])
def test_catalog_preserves_reported_support_restrictions_and_host_tags(monkeypatch, season):
    monkeypatch.setattr(season_manager, 'get_active_season', lambda: season)
    catalog = get_skills()
    skills = {s['item_id']: s for s in catalog['skills']}
    # Canonical tli-data _skills.json in both hydrated seasons, not tooltip inference.
    assert catalog['season'] == season
    assert skills['willpower']['name'] == 'Willpower'
    assert skills['willpower']['description_lines'][0] == 'Supports Attack and Spell Skills.'
    assert skills['thunder_spike']['skill_tags'] == ['Attack', 'Lightning', 'Area', 'Melee', 'Shadow Strike']
    assert skills['periodic_burst']['name'] == 'Periodic Burst'
    assert skills['periodic_burst']['description_lines'][0] == 'Support Mobility Skills.'
    assert skills['spiral_strike']['skill_tags'] == ['Attack', 'Erosion', 'Area', 'Melee', 'Mobility']
