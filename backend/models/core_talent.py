from dataclasses import dataclass, field


@dataclass
class CoreTalent:
    id: str
    name: str
    effects: list[str] = field(default_factory=list)


@dataclass
class CoreTalentSlot:
    threshold: int          # total points required to unlock this slot
    options: list[CoreTalent]
    selected_id: str | None = None

    @property
    def is_selected(self) -> bool:
        return self.selected_id is not None

    def selected_talent(self) -> "CoreTalent | None":
        if self.selected_id is None:
            return None
        return next((t for t in self.options if t.id == self.selected_id), None)
