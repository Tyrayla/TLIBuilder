import tkinter as tk
from trees.registry import TREES

BG_SIDE   = "#111122"
BG_BTN    = "#1a1a2e"
FG_DIM    = "#888899"
FG_SLOT   = "#aaaacc"
FG_HEADER = "#e0e0e0"
ACCENT    = "#e94560"
SIDEBAR_W = 170


class ActiveTreesSidebar(tk.Frame):
    def __init__(self, parent, app, on_overview=None, current_tree: str | None = None):
        super().__init__(parent, bg=BG_SIDE, width=SIDEBAR_W)
        self.app = app
        self._on_overview = on_overview
        self._current_tree = current_tree
        self._slot_borders: list[tk.Frame] = []
        self._slot_btns: list[tk.Button] = []
        self.pack_propagate(False)
        self._build()

    def _build(self):
        tk.Label(self, text="Active Trees",
                 font=("Segoe UI", 10, "bold"),
                 bg=BG_SIDE, fg=FG_DIM).pack(pady=(12, 6))

        tk.Button(
            self, text="Overview",
            font=("Segoe UI", 10), bg=BG_BTN, fg=FG_HEADER,
            activebackground="#0f3460", activeforeground=FG_HEADER,
            relief="flat", bd=0, padx=8, pady=6,
            cursor="hand2",
            command=self._overview_clicked,
        ).pack(fill="x", padx=8, pady=(0, 10))

        tk.Frame(self, bg="#333355", height=1).pack(fill="x", padx=8, pady=4)

        for i in range(4):
            border = tk.Frame(self, bg=self._slot_border_color(i), padx=2, pady=2)
            border.pack(fill="x", padx=8, pady=3)
            self._slot_borders.append(border)

            btn = tk.Button(
                border,
                text=self._slot_label(i),
                font=("Segoe UI", 9),
                bg=BG_BTN, fg=FG_SLOT,
                activebackground="#0f3460", activeforeground=FG_HEADER,
                relief="flat", bd=0, padx=6, pady=8,
                wraplength=SIDEBAR_W - 24,
                cursor="hand2",
                command=lambda idx=i: self._open_slot(idx),
            )
            btn.pack(fill="x")
            self._slot_btns.append(btn)

    def _slot_label(self, idx: int) -> str:
        val = self.app.selected_trees[idx]
        return val if val is not None else "— Empty —"

    def _slot_border_color(self, idx: int) -> str:
        name = self.app.selected_trees[idx]
        if name is None:
            return "#2a2a3a"
        if name == self._current_tree:
            return "#c8c8d8"
        return TREES[name]["color"]

    def refresh(self):
        for i, (border, btn) in enumerate(zip(self._slot_borders, self._slot_btns)):
            btn.config(text=self._slot_label(i))
            border.config(bg=self._slot_border_color(i))

    def _overview_clicked(self):
        if self._on_overview:
            self._on_overview()

    def _open_slot(self, idx: int):
        val = self.app.selected_trees[idx]
        if val is not None:
            tree = TREES[val]["builder"]()
            self.app.show_tree_viewer(tree)
        elif self._on_overview:
            self._on_overview()
