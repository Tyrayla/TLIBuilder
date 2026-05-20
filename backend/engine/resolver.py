from __future__ import annotations
import re

from engine.models import BuildInput, ComputedResult
from engine.aggregator import aggregate
from engine.pipeline import run_pipeline


def _slug(tree_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", tree_name.lower()).strip("_")


def compute(build: BuildInput) -> ComputedResult:
    """
    Public entry point. Loads season tree data and filter recipes, aggregates
    stats from all build sources, runs the damage pipeline, and returns the result.
    """
    from persistence import season_manager
    from tools.node_type_filter_builder import load_filter

    # Load node_type_filter recipes
    filter_data = load_filter() or {}

    # Collect tree slugs needed from talent slots + slates
    needed_slugs: set[str] = set()
    for slot in build.slots:
        if slot and slot.get("treeName"):
            needed_slugs.add(_slug(slot["treeName"]))

    for slate in build.slates:
        for slot_data in slate.get("slots", []):
            node_id = slot_data.get("selectedNodeId")
            if node_id:
                m = re.match(r"^(.+)_c\d+_r\d+$", node_id)
                if m:
                    needed_slugs.add(m.group(1))

    # Load season tree data for every needed tree
    season_trees: dict[str, dict] = {}
    for slug in needed_slugs:
        tree_data = season_manager.load_season_tree(build.season, slug)
        if tree_data:
            season_trees[slug] = tree_data

    # Aggregate → Pipeline
    source = aggregate(build, season_trees, filter_data)
    return run_pipeline(source, build.skill, build.enemy)
