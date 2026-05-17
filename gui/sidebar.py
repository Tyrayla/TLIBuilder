import tkinter as tk
from trees.registry import TREES

BG_SIDE   = "#111122"
BG_BTN    = "#1a1a2e"
FG_DIM    = "#888899"
FG_SLOT   = "#aaaacc"
FG_HEADER = "#e0e0e0"
ACCENT    = "#e94560"
SIDEBAR_W = 150


class ActiveTreesSidebar(tk.Frame):
    def __init__(self, parent, app, on_overview=None):
        super().__init__(parent, bg=BG_SIDE, width=SIDEBAR_W)
        self.app = app
        self._on_overview = on_overview
        self._slot_btns: list[tk.Button] = []
        self.pack_propagate(False)
        self._build()

    def _build(self):
        tk.Label(self, text="Active Trees",
                 font=("Segoe UI", 9, "bold"),
                 bg=BG_SIDE, fg=FG_DIM).pack(pady=(12, 6))

        tk.Button(
            self, text="Overview",
            font=("Segoe UI", 9), bg=BG_BTN, fg=FG_HEADER,
            activebackground="#0f3460", activeforeground=FG_HEADER,
            relief="flat", bd=0, padx=8, pady=6,
            cursor="hand2",
            command=self._overview_clicked,
        ).pack(fill="x", padx=8, pady=(0, 10))

        tk.Frame(self, bg="#333355", height=1).pack(fill="x", padx=8, pady=4)

        for i in range(4):
            btn = tk.Button(
                self,
                text=self._slot_label(i),
                font=("Segoe UI", 8),
                bg=BG_BTN, fg=FG_SLOT,
                activebackground="#0f3460", activeforeground=FG_HEADER,
                relief="flat", bd=0, padx=6, pady=8,
                wraplength=SIDEBAR_W - 20,
                cursor="hand2",
                command=lambda idx=i: self._open_slot(idx),
            )
            btn.pack(fill="x", padx=8, pady=3)
            self._slot_btns.append(btn)

    def _slot_label(self, idx: int) -> str:
        val = self.app.selected_trees[idx]
        return val if val is not None else "— Empty —"

    def refresh(self):
        for i, btn in enumerate(self._slot_btns):
            btn.config(text=self._slot_label(i))

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
