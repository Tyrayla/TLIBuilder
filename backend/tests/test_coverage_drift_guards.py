"""Drift guards for two hand-maintained / structural invariants behind `engine.coverage`'s hero-trait
coverage honesty (docs/BACKLOG.md §8 #3 and #5). Both protect `trait_coverage`'s guarantee that a trait
only reads 'full' when the build-independent probe genuinely saw every pick-/context-gated line.

Mirrors `test_consumable_universe.py`'s "every literal the code reads is accounted for" style, applied to
the hero-trait advanced-pick list and the `status_lines` signatures instead of the aggregator scan.
"""
import ast
import glob
import inspect
import os
import re
import textwrap

from engine import hero_traits
from engine.coverage import _ALL_ADVANCED_PICKS

_HERO_TRAITS_DIR = os.path.dirname(hero_traits.__file__)
# Modules check picks as string literals: `"<Name>" in picks` (picks = set(advanced_picks or [])).
_PICK_IN_PICKS_RE = re.compile(r'"([^"]+)"\s+in\s+picks\b')


def _referenced_pick_names() -> set[str]:
    """Every advanced-pick name any hero_traits/*.py module actually gates on, scraped from source."""
    names: set[str] = set()
    for path in glob.glob(os.path.join(_HERO_TRAITS_DIR, "*.py")):
        if os.path.basename(path) in ("__init__.py", "_catalog.py"):
            continue
        with open(path, encoding="utf-8") as f:
            names |= set(_PICK_IN_PICKS_RE.findall(f.read()))
    return names


# ── #3: `_ALL_ADVANCED_PICKS` mirror must not drift from the modules it probes ───────────────────
class TestAdvancedPicksDrift:
    def test_scan_finds_pick_checks(self):
        """Guard the guard: if this scan ever returns nothing, the modules changed how they gate picks
        and the two assertions below would pass vacuously."""
        assert _referenced_pick_names(), (
            'no `"..." in picks` checks found in hero_traits/*.py — the gating pattern changed; update '
            "_PICK_IN_PICKS_RE so this drift guard keeps working."
        )

    def test_every_module_pick_is_in_all_advanced_picks(self):
        """The forward drift: a module gates on a pick name absent from `_ALL_ADVANCED_PICKS`, so
        `trait_coverage`'s pick-everything probe never enables it → a pick-gated warning/NYI branch goes
        unseen and the trait can silently overclaim 'full'."""
        missing = _referenced_pick_names() - set(_ALL_ADVANCED_PICKS)
        assert not missing, (
            f"hero-trait modules gate on advanced picks missing from coverage._ALL_ADVANCED_PICKS: "
            f"{sorted(missing)} — add them so trait_coverage probes them."
        )

    def test_all_advanced_picks_has_no_stale_entries(self):
        """The reverse drift: a tuple entry no module checks anymore (renamed/removed pick). Harmless to
        the probe, but a dead entry masks the mirror's intent — prune it."""
        stale = set(_ALL_ADVANCED_PICKS) - _referenced_pick_names()
        assert not stale, (
            f"coverage._ALL_ADVANCED_PICKS has entries no module gates on via `\"...\" in picks`: "
            f"{sorted(stale)} — a renamed/removed pick left a dead entry; prune or fix."
        )


# ── #5: `status_lines` must declare build-specific inputs by NAME, not read them from **kwargs ────
# Build-specific inputs describe ANOTHER equipped entity (the main skill, other slots). trait_coverage's
# single-argument probe leaves them at default, and hero_traits.build_gated_status_params only sees them
# when they're NAMED params (it excludes VAR_KEYWORD). A module that reaches into its catch-all `**kw`
# for one of these hides a build-gated branch from the detector → trait_coverage could overclaim 'full'.
_BUILD_SPECIFIC_KEYS = {
    "main_skill_tags", "main_skill_name", "attached_supports",
    "skills_input", "skills_by_id", "prepared_skill",
}


class TestStatusLinesKwargsLoophole:
    def _kwarg_reads(self, fn):
        """Yield build-specific keys read DIRECTLY out of `status_lines`' VAR_KEYWORD param — a
        `kw["key"]` subscript or a `kw.get/pop/setdefault("key")` call. Deliberately narrow: it does
        NOT chase the kwarg through an alias (`d = _; d["main_skill_tags"]`) or a re-splat into a
        helper (`_build(**_)`). Those obfuscated shapes also evade the production
        `hero_traits.build_gated_status_params` detector this guard mirrors, so they are the same
        pre-existing loophole, not something this test regresses; the direct read is the shape that
        actually occurs and is worth pinning."""
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        except (OSError, TypeError, SyntaxError):
            return
        funcdef = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "status_lines"),
            None,
        )
        if funcdef is None or funcdef.args.kwarg is None:
            return
        kw = funcdef.args.kwarg.arg  # e.g. "_"
        for node in ast.walk(funcdef):
            key = None
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                    and node.value.id == kw and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                key = node.slice.value  # kw["main_skill_tags"]
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == kw
                    and node.func.attr in ("get", "pop", "setdefault")
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                key = node.args[0].value  # kw.get("main_skill_tags")
            if key in _BUILD_SPECIFIC_KEYS:
                yield key

    def test_no_module_reads_build_specific_state_via_kwargs(self):
        offenders = []
        for trait_id, fn in hero_traits._STATUS.items():
            for key in self._kwarg_reads(fn):
                offenders.append(f"{trait_id}: reads build-specific '{key}' from **kwargs")
        assert not offenders, (
            "a hero-trait status_lines reads build-specific state through **kwargs instead of a named "
            "parameter, hiding it from hero_traits.build_gated_status_params so trait_coverage could "
            "overclaim 'full':\n  " + "\n  ".join(sorted(set(offenders)))
            + "\nDeclare these as named parameters instead."
        )

    def test_at_least_one_status_lines_probed(self):
        """Guard the guard: ensure the registry is non-empty so the sweep above isn't vacuous."""
        assert hero_traits._STATUS, "no status_lines registered — the kwargs sweep would be vacuous"
