# ── NO MANUAL WORK REQUIRED ───────────────────────────────────────────────────
# Aggregates StatContribution objects from all registered providers.
# Flow:
#   1. Create a CharacterSheet
#   2. Register every active provider (gear slots, passive tree, core talents,
#      base stats) — providers return [] when inactive so always register all
#   3. Call get_stat(Stat.X) anywhere a formula needs a value
#   4. Call get_breakdown(Stat.X) to show the user all sources of a stat
# StatProvider is a structural protocol — any object with a contributions()
# method qualifies; no explicit inheritance needed.
# ──────────────────────────────────────────────────────────────────────────────
from typing import Protocol, runtime_checkable
from models.stat import Stat
from models.stat_contribution import StatContribution


@runtime_checkable
class StatProvider(Protocol):
    def contributions(self) -> list[StatContribution]: ...


class CharacterSheet:
    def __init__(self):
        self._providers: list[StatProvider] = []

    def register(self, provider: StatProvider) -> None:
        self._providers.append(provider)

    def get_stat(self, stat: Stat) -> float:
        total = 0.0
        for provider in self._providers:
            for c in provider.contributions():
                if c.stat == stat:
                    total += c.value
        return total

    def get_breakdown(self, stat: Stat) -> list[StatContribution]:
        return [
            c
            for provider in self._providers
            for c in provider.contributions()
            if c.stat == stat
        ]

    def all_stats(self) -> dict[Stat, float]:
        result: dict[Stat, float] = {}
        for provider in self._providers:
            for c in provider.contributions():
                result[c.stat] = result.get(c.stat, 0.0) + c.value
        return result
