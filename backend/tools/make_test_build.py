"""make_test_build.py — dev-only: build a real, engine-computed test build without touching the UI.

Exists because manually clicking through New Build → Hero Trait → Skills → Import/Export in a live
app instance to produce one throwaway test build/share-link is slow, and (worse) each such instance
is a real, visible Electron window that has to be tracked and closed by hand (see the 2026-09-13
incident where several got left running). This script does the same job — hero + trait + advanced
picks + main skill → a real `tli1_` code, computed via the ACTUAL engine (`engine.compute.compute`,
same call the app itself makes), with an optional direct POST to the share service — in one process,
with no window, no clicking, and nothing left running afterward.

Scope, deliberately narrow:
  - No gear. `buildGearPayload`'s weapon-averaging/contribution logic
    (src/renderer/src/utils/statsPayload.ts) is real per-item engine-input translation, not
    something to re-implement here — a build needing specific gear is still fastest to finish by
    hand in the app, using the code this script prints as the starting point (paste into Import).
  - `trait_slot_levels` defaults to all-active ([1,1,1,1]) — i.e. as if a Hero Memory were socketed
    at every advanced tier. The real app derives this from actually-socketed memories
    (HeroTraitScreen.tsx's `deriveTraitSlotLevels`) and shows a tier as OFF with none socketed; this
    script skips that derivation entirely. Pass --slot-levels to override (e.g. "1,0,0,0" to match a
    build with no memories socketed at all).
  - `trait_effects` is left empty. Fine for a bespoke trait (one with its own
    backend/engine/hero_traits/<x>.py module, dispatched by trait_id) — it doesn't read that field.
    A non-bespoke trait's advanced-pick text would need it; out of scope for now.

Usage (from backend/):
    python tools/make_test_build.py --trait seething_silhouette --picks "Fury's Onslaught,Hysteria,Rage Infusion" \
        --skill berserking_blade --level 90 --name "Rehan test"

    # Also create a real share link (posts to the live share service):
    python tools/make_test_build.py --trait seething_silhouette --skill berserking_blade --share

Prints the `tli1_` code always; prints the computed preview fields always; prints the share id/url
only with --share.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ — matches other tools/ scripts

from build_code import encode_build  # noqa: E402

DEFAULT_SHARE_BASE = "https://api.tlibuilder.com"


def _active_season() -> str:
    from persistence import season_manager
    season = season_manager.get_active_season()
    if not season:
        raise SystemExit("No active season configured — check data/seasons/ and the active-season setting.")
    return season


def _find_trait(trait_id: str) -> dict:
    from persistence import season_manager
    season = _active_season()
    indexed = season_manager.load_hero_traits_indexed(season)
    trait = indexed.get(trait_id)
    if trait is None:
        raise SystemExit(f"Unknown trait_id {trait_id!r} in season {season!r} — check data/seasons/<season>/_hero_traits.json")
    return trait


def _find_skill(skill_id: str) -> dict:
    from server import _get_skills_data
    season = _active_season()
    skill = _get_skills_data(season).get(skill_id)
    if skill is None:
        raise SystemExit(f"Unknown skill item_id {skill_id!r} in season {season!r} — check data/seasons/<season>/_skills.json")
    return skill


def build_dict(args: argparse.Namespace, skill: dict) -> dict:
    # name/skill_tags/description_lines are required on every real EquippedSkill (SkillsScreen.tsx reads
    # them unconditionally) — neither build_code.py's decode nor buildStore.loadBuild back-fills them, so
    # omitting them here would crash the Skills screen the moment this code is pasted into Import.
    return {
        "buildName": args.name,
        "activeSlot": 0,
        "slots": [None, None, None, None],
        "slates": [], "slateInventory": [], "prisms": [], "prismInventory": [], "conditionState": {},
        "gear": [],
        "skills": [{
            "item_id": args.skill, "slot": 1, "level": args.skill_level, "supports": [],
            "name": skill.get("name", args.skill),
            "skill_tags": skill.get("skill_tags", []),
            "description_lines": skill.get("description_lines", []),
        }],
        "characterLevel": args.level,
        "traitId": args.trait,
        "traitSlotLevels": args.slot_levels,
        "advancedTraitSelections": args.picks,
        "traitTreeAllocations": [], "traitSkillSupports": [], "licoricePreparedSkill": None, "elixirIngredients": {},
        "heroMemories": [None, None, None], "baseMemory": None, "memoryInventory": [],
        "pactSpirits": [None, None, None], "fates": {}, "undetermined": [None, None, None],
        "notes": "", "customMods": [],
        "targetConfig": None, "enemyConfig": None,
    }


def _character_contributions(level: int) -> list[dict]:
    """Base per-level character stats (life/mana/energy) — mirrors
    src/renderer/src/api/client.ts's buildCharacterContributions with gear=[] (no gear-slot energy
    bonus to add). Plain arithmetic straight from the Help DB formulas, not engine logic — safe to
    keep in sync here rather than pulling in the real gear-contribution pipeline for this alone."""
    lvl = min(max(level, 0), 100)
    levels_gained = max(lvl - 1, 0)
    base_life = 50 + 13 * levels_gained
    base_mana = 40 + 5 * levels_gained
    contribs = [
        {"stat": "max_life_flat", "amount": base_life, "label": "Base", "text": f"+{base_life} Max Life (50 + 13/level)"},
        {"stat": "max_mana_flat", "amount": base_mana, "label": "Base", "text": f"+{base_mana} Max Mana (40 + 5/level)"},
        {"stat": "max_energy_flat", "amount": 4, "label": "Base", "text": "+4 Max Energy"},
    ]
    if lvl > 0:
        contribs.append({"stat": "max_energy_flat", "amount": lvl, "label": "Levels", "text": f"+{lvl} Max Energy"})
    base_evasion = 2 * levels_gained
    if base_evasion > 0:
        contribs.append({"stat": "evasion_flat", "amount": base_evasion, "label": "Base", "text": f"+{base_evasion} Evasion (2/level)"})
    return contribs


def compute_preview(args: argparse.Namespace, trait: dict, skill: dict) -> dict:
    """Call the real engine in-process (server.py's engine_stats — same function the app's
    /api/engine/stats route calls) to get genuinely computed stats, then shape them into the
    share service's PreviewPayload fields. Mirrors the client-side mapping the share-overview-preview
    feature's ImportExportOverlay.tsx (buildSharePreview) sends at share time — that feature isn't
    merged to dev/dev2 yet, so this is currently the only thing exercising that half of the contract."""
    from server import engine_stats, EngineStatsRequest, SkillSlotInput, SkillEngineInput

    req = EngineStatsRequest(
        slots=[None, None, None, None],
        gear=[],
        character=_character_contributions(args.level),
        main_skill=SkillEngineInput(skill_id=args.skill, level=args.skill_level),
        skills=[SkillSlotInput(slot=1, skill_id=args.skill, level=args.skill_level, enabled=True)],
        characterLevel=args.level,
        trait_id=args.trait,
        trait_slot_levels=args.slot_levels,
        advanced_trait_selections=args.picks,
    )
    result = engine_stats(req)
    defense = result["defense"]
    offense = result["offense"]
    stats = result["stats"]

    icon_url = trait.get("icon_url")
    # Same allowlist the share service enforces — omit rather than send a URL it will reject.
    if not icon_url or not icon_url.startswith("https://tlibuilder-data.pages.dev/icons/"):
        icon_url = None

    movement_speed = 0.0
    ms_entry = stats.get("movement_speed")
    if ms_entry is not None:
        movement_speed = ms_entry.get("total", 0.0) if isinstance(ms_entry, dict) else getattr(ms_entry, "total", 0.0)
        movement_speed = movement_speed or 0.0

    return {
        "hero": trait.get("hero", ""),
        "trait": trait.get("variant_name", args.trait),
        "level": args.level,
        "main_skill": skill.get("name", args.skill),
        "icon_url": icon_url,
        "max_life": defense["max_life"],
        "max_mana": defense["max_mana"],
        "max_energy_shield": defense["max_energy_shield"],
        "total_dps": offense["total_dps_vs_target"],
        "fire_resist": defense["fire_resist"],
        "cold_resist": defense["cold_resist"],
        "lightning_resist": defense["lightning_resist"],
        "erosion_resist": defense["erosion_resist"],
        "movement_speed": movement_speed,
    }


def post_share(share_base: str, code: str, preview: dict) -> dict:
    import ssl
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()

    body = json.dumps({"code": code, "preview": preview}).encode("utf-8")
    req = urllib.request.Request(
        f"{share_base}/b", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Share service rejected the request ({exc.code}): {detail}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach the share service at {share_base}: {exc.reason}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trait", required=True, help="Hero-trait trait_id, e.g. seething_silhouette")
    p.add_argument("--picks", default="", help="Comma-separated advanced-trait pick names, e.g. \"Fury's Onslaught,Hysteria\"")
    p.add_argument("--slot-levels", default="1,1,1,1", help="Comma-separated [base,lv45,lv60,lv75] levels, 0=off. Default: all active at 1.")
    p.add_argument("--skill", required=True, help="Main-skill item_id, e.g. berserking_blade")
    p.add_argument("--skill-level", type=int, default=20)
    p.add_argument("--level", type=int, default=90, help="Character level")
    p.add_argument("--name", default="Dev test build")
    p.add_argument("--share", action="store_true", help="POST to the share service and print the real link")
    p.add_argument("--share-base", default=DEFAULT_SHARE_BASE)
    args = p.parse_args()

    if not (1 <= args.level <= 100):
        raise SystemExit(f"--level must be between 1 and 100, got {args.level}")

    args.picks = [s.strip() for s in args.picks.split(",") if s.strip()]
    try:
        args.slot_levels = [int(x.strip()) for x in args.slot_levels.split(",")]
    except ValueError:
        raise SystemExit(f"--slot-levels must be 4 comma-separated integers, got {args.slot_levels!r}")
    if len(args.slot_levels) != 4:
        raise SystemExit("--slot-levels must have exactly 4 comma-separated values")

    trait = _find_trait(args.trait)
    skill = _find_skill(args.skill)

    code = encode_build(build_dict(args, skill))
    print(f"CODE:\n{code}\n")

    preview = compute_preview(args, trait, skill)
    print("PREVIEW (real engine-computed stats):")
    print(json.dumps(preview, indent=2))

    if args.share:
        if args.share_base == DEFAULT_SHARE_BASE:
            print(f"\nPosting to the PRODUCTION share service ({DEFAULT_SHARE_BASE}) — this writes a real, permanent row.")
        result = post_share(args.share_base, code, preview)
        print(f"\nSHARE LINK: {result['url']}")


if __name__ == "__main__":
    main()
