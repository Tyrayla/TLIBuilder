import tkinter as tk
from models.passive_tree import PassiveTree, COLUMN_COUNT
from persistence import save_manager

COLUMN_LABELS = [col * 3 for col in range(COLUMN_COUNT)]

BG_MAIN        = "#1a1a2e"
BG_COLUMN      = "#16213e"
BG_COL_LOCKED  = "#111111"
FG_HEADER      = "#e0e0e0"
FG_LOCKED_TEXT = "#444444"
BTN_NORMAL_BG  = "#0f3460"
BTN_NORMAL_FG  = "#e0e0e0"
BTN_FULL_BG    = "#533483"
BTN_FULL_FG    = "#ffffff"
BTN_LOCKED_BG  = "#222222"
BTN_LOCKED_FG  = "#444444"
ACCENT         = "#e94560"
STATUS_ERROR   = "#ff6b6b"
STATUS_OK      = "#6bcb77"
TOOLTIP_BG     = "#0d1b2a"
TOOLTIP_FG     = "#e0e0e0"
TOOLTIP_BORDER = "#e94560"


# ── Tooltip ────────────────────────────────────────────────────────────────────

class Tooltip:
    def __init__(self, widget: tk.Widget, text_func):
        self._widget = widget
        self._text_func = text_func
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, event: tk.Event):
        text = self._text_func()
        if not text:
            return
        self._hide(None)
        x = event.x_root + 16
        y = event.y_root + 12
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg=TOOLTIP_BORDER)
        inner = tk.Frame(tw, bg=TOOLTIP_BG, padx=8, pady=6)
        inner.pack(padx=1, pady=1)
        tk.Label(inner, text=text, justify="left",
                 bg=TOOLTIP_BG, fg=TOOLTIP_FG,
                 font=("Segoe UI", 9)).pack()

    def _hide(self, event):
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ── Tree viewer ────────────────────────────────────────────────────────────────

class TreeViewer(tk.Frame):
    def __init__(self, parent, app, tree: PassiveTree):
        super().__init__(parent, bg=BG_MAIN)
        self.app = app
        self.tree = tree
        self._build_header()
        self._build_columns()
        self._build_status_bar()
        self._refresh()

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self):
        frame = tk.Frame(self, bg=BG_MAIN, pady=8)
        frame.pack(fill="x", padx=12)

        # Back button — top left
        tk.Button(
            frame, text="← Back",
            font=("Segoe UI", 9), bg=BG_MAIN, fg=FG_HEADER,
            activebackground="#0f3460", activeforeground=FG_HEADER,
            relief="flat", bd=0, cursor="hand2",
            command=self.app.show_tree_selector,
        ).pack(side="left", padx=(0, 12))

        tk.Label(frame, text=self.tree.name,
                 font=("Segoe UI", 16, "bold"),
                 bg=BG_MAIN, fg=ACCENT).pack(side="left")

        # Reset button — top right
        tk.Button(
            frame, text="Reset",
            font=("Segoe UI", 9), bg="#3a1a1a", fg="#ff6b6b",
            activebackground=ACCENT, activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._reset,
        ).pack(side="right", padx=(8, 0))

        self.points_label = tk.Label(frame, text="Points: 0",
                                     font=("Segoe UI", 12),
                                     bg=BG_MAIN, fg=FG_HEADER)
        self.points_label.pack(side="right")

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        self.status_bar = tk.Label(self, text="",
                                   font=("Segoe UI", 9, "italic"),
                                   bg=BG_MAIN, fg=STATUS_ERROR,
                                   anchor="w", padx=14, pady=4)
        self.status_bar.pack(fill="x", side="bottom")

    def _set_status(self, message: str, error: bool = True):
        self.status_bar.config(text=message,
                               fg=STATUS_ERROR if error else STATUS_OK)
        if message:
            self.after(3000, lambda: self.status_bar.config(text=""))

    # ── Columns ────────────────────────────────────────────────────────────────

    def _build_columns(self):
        container = tk.Frame(self, bg=BG_MAIN)
        container.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        self.col_frames: dict[int, tk.LabelFrame] = {}
        self.col_lock_labels: dict[int, tk.Label] = {}
        self.node_buttons: dict[str, tk.Button] = {}
        self._tooltips: dict[str, Tooltip] = {}

        for col in range(COLUMN_COUNT):
            label = COLUMN_LABELS[col]
            lf = tk.LabelFrame(container, text=f"  {label}  ",
                               font=("Segoe UI", 10, "bold"),
                               bg=BG_COLUMN, fg=FG_HEADER,
                               padx=8, pady=8, relief="ridge", bd=2)
            lf.pack(side="left", fill="both", expand=True, padx=4)
            self.col_frames[col] = lf

            lock_lbl = tk.Label(lf, text="", bg=BG_COLUMN, fg=FG_LOCKED_TEXT,
                                font=("Segoe UI", 9, "italic"))
            lock_lbl.pack()
            self.col_lock_labels[col] = lock_lbl

            for node in self.tree.nodes_in_column(col):
                btn = tk.Button(lf, text=self._node_label(node),
                                font=("Segoe UI", 9),
                                width=14, wraplength=100,
                                relief="raised", bd=2, cursor="hand2")
                btn.pack(pady=4)
                btn.bind("<Button-1>", lambda e, nid=node.id: self._on_left_click(nid))
                btn.bind("<Button-3>", lambda e, nid=node.id: self._on_right_click(nid))
                self.node_buttons[node.id] = btn
                self._tooltips[node.id] = Tooltip(
                    btn, text_func=lambda nid=node.id: self._tooltip_text(nid))

    # ── Tooltip ────────────────────────────────────────────────────────────────

    def _tooltip_text(self, node_id: str) -> str:
        node = self.tree.nodes.get(node_id)
        if node is None:
            return ""
        pts = node.current_points
        mx  = node.max_points
        header  = f"{node.node_type.value:<28}{pts}/{mx}"
        divider = "─" * len(header)
        lines = [header, divider,
                 f"Current ({pts} pt{'s' if pts != 1 else ''}):",
                 "  — No stats assigned —"]
        if not node.is_full:
            lines += ["",
                      f"Next ({pts + 1} pt{'s' if pts + 1 != 1 else ''}):",
                      "  — No stats assigned —"]
        return "\n".join(lines)

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _refresh(self):
        self.points_label.config(text=f"Points: {self.tree.total_points()}")

        for col in range(COLUMN_COUNT):
            unlocked = self.tree.is_column_unlocked(col)
            lf = self.col_frames[col]
            lock_lbl = self.col_lock_labels[col]

            if unlocked:
                lf.config(bg=BG_COLUMN, fg=FG_HEADER)
                col_pts = self.tree.points_in_column(col)
                lock_lbl.config(
                    text=f"{col_pts}/3 to advance" if col < COLUMN_COUNT - 1 else "",
                    bg=BG_COLUMN, fg=FG_LOCKED_TEXT)
            else:
                lf.config(bg=BG_COL_LOCKED, fg=FG_LOCKED_TEXT)
                lock_lbl.config(text="LOCKED", bg=BG_COL_LOCKED, fg=FG_LOCKED_TEXT)

            for node in self.tree.nodes_in_column(col):
                btn = self.node_buttons[node.id]
                btn.config(text=self._node_label(node))
                if not unlocked:
                    btn.config(state="disabled", bg=BTN_LOCKED_BG, fg=BTN_LOCKED_FG,
                               activebackground=BTN_LOCKED_BG)
                elif node.is_full:
                    btn.config(state="normal", bg=BTN_FULL_BG, fg=BTN_FULL_FG,
                               activebackground=BTN_FULL_BG)
                else:
                    btn.config(state="normal", bg=BTN_NORMAL_BG, fg=BTN_NORMAL_FG,
                               activebackground=BTN_NORMAL_BG)

    def _node_label(self, node) -> str:
        return f"{node.node_type.value}\n{node.current_points}/{node.max_points}"

    # ── Click handlers ─────────────────────────────────────────────────────────

    def _on_left_click(self, node_id: str):
        try:
            self.tree.allocate(node_id)
            self._save()
            self._set_status("")
        except ValueError as e:
            self._set_status(str(e), error=True)
        self._refresh()

    def _on_right_click(self, node_id: str):
        try:
            self.tree.deallocate(node_id)
            self._save()
            self._set_status("")
        except ValueError as e:
            self._set_status(str(e), error=True)
        self._refresh()

    def _reset(self):
        for node in self.tree.nodes.values():
            node.current_points = 0
        self._save()
        self._refresh()
        self._set_status("All points reset.", error=False)

    def _save(self):
        node_points = {nid: n.current_points for nid, n in self.tree.nodes.items()}
        save_manager.save(self.tree.name, node_points)
