import tkinter as tk
import inspect
import re
from models.passive_tree import PassiveTree, COLUMN_COUNT
from models.passive_node import NodeType, NodeStat
from models.stat import Stat
from models.stat_meta import STAT_META, CATEGORIES
from data.node_modifier_pool import NODE_MODIFIER_POOL
from persistence import save_manager, node_stats_manager
from gui.sidebar import ActiveTreesSidebar
from trees.registry import TREES

COLUMN_LABELS = [col * 3 for col in range(COLUMN_COUNT)]
ROW_COUNT = 5
HEADER_H  = 32   # px at top of canvas for column label + lock text
NODE_R    = 32   # circle radius (diameter = 64 px)

BG_MAIN        = "#1a1a2e"
FG_HEADER      = "#e0e0e0"
FG_LOCKED_TEXT = "#666677"
BTN_NORMAL_BG  = "#0f3460"
BTN_NORMAL_FG  = "#e0e0e0"
BTN_NORMAL_OUT = "#3a5a9a"
BTN_FULL_BG    = "#533483"
BTN_FULL_FG    = "#ffffff"
BTN_FULL_OUT   = "#e94560"
BTN_LOCKED_BG  = "#222233"
BTN_LOCKED_FG  = "#444455"
BTN_LOCKED_OUT = "#333344"
ACCENT         = "#e94560"
STATUS_ERROR   = "#ff6b6b"
STATUS_OK      = "#6bcb77"
CONN_COLOR     = "#3a3a5a"
TOOLTIP_BG     = "#0d1b2a"
TOOLTIP_FG     = "#e0e0e0"
TOOLTIP_BORDER = "#e94560"
DEBUG_BAR_BG   = "#0d1520"
LINK_PENDING   = "#ffcc00"


# ── Canvas tooltip ─────────────────────────────────────────────────────────────

class CanvasTooltip:
    def __init__(self, canvas: tk.Canvas, tag: str, text_func):
        self._canvas = canvas
        self._text_func = text_func
        self._tip: tk.Toplevel | None = None
        self._label: tk.Label | None = None
        canvas.tag_bind(tag, "<Enter>", self._show, add="+")
        canvas.tag_bind(tag, "<Leave>", self._hide, add="+")
        # No ButtonPress hide — tooltip stays open after a click so the
        # updated pts/max value is immediately visible without re-hovering.

    def _show(self, event: tk.Event):
        text = self._text_func()
        if not text:
            return
        if self._tip:
            self.refresh()
            return
        self._tip = tw = tk.Toplevel(self._canvas)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{event.x_root + 16}+{event.y_root + 12}")
        tw.configure(bg=TOOLTIP_BORDER)
        inner = tk.Frame(tw, bg=TOOLTIP_BG, padx=6, pady=4)
        inner.pack(padx=1, pady=1)
        self._label = tk.Label(inner, text=text, justify="left",
                               bg=TOOLTIP_BG, fg=TOOLTIP_FG,
                               font=("Segoe UI", 8))
        self._label.pack()

    def refresh(self):
        if self._tip and self._label:
            self._label.config(text=self._text_func())

    def _hide(self, event):
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ── Tree viewer ────────────────────────────────────────────────────────────────

class TreeViewer(tk.Frame):
    def __init__(self, parent, app, tree: PassiveTree):
        super().__init__(parent, bg=BG_MAIN)
        self.app  = app
        self.tree = tree

        self._debug_mode = False
        self._link_mode  = False
        self._type_mode  = False
        self._stat_mode  = False
        self._link_first: str | None = None
        self._source_file: str | None = None

        entry = TREES.get(tree.name)
        if entry:
            try:
                self._source_file = inspect.getfile(entry["builder"])
            except (TypeError, OSError):
                pass

        main_row = tk.Frame(self, bg=BG_MAIN)
        main_row.pack(fill="both", expand=True)

        sidebar = ActiveTreesSidebar(
            main_row, app,
            on_overview=app.show_tree_selector,
            current_tree=self.tree.name,
        )
        sidebar.pack(side="left", fill="y")

        content = tk.Frame(main_row, bg=BG_MAIN)
        content.pack(side="left", fill="both", expand=True)
        content.grid_rowconfigure(2, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self._build_header(content)
        self._build_debug_bar(content)
        self._build_canvas(content)
        self._build_status_bar(content)
        self._load_node_stats()
        self._refresh()

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self, parent):
        frame = tk.Frame(parent, bg=BG_MAIN, pady=8)
        frame.grid(row=0, column=0, sticky="ew", padx=12)

        # Left: back button + tree name
        left = tk.Frame(frame, bg=BG_MAIN)
        left.pack(side="left")
        tk.Button(
            left, text="← Back",
            font=("Segoe UI", 9), bg=BG_MAIN, fg=FG_HEADER,
            activebackground="#0f3460", activeforeground=FG_HEADER,
            relief="flat", bd=0, cursor="hand2",
            command=self.app.show_tree_selector,
        ).pack(side="left", padx=(0, 12))
        tk.Label(left, text=self.tree.name,
                 font=("Segoe UI", 16, "bold"),
                 bg=BG_MAIN, fg=TREES[self.tree.name]["color"]).pack(side="left")

        self._ct_btn = tk.Button(
            left, text=self._ct_btn_label(),
            font=("Segoe UI", 9), bg="#1e0e3a", fg="#c084fc",
            activebackground="#3b1f6e", activeforeground="#e9d5ff",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._open_core_talent_overlay,
        )
        self._ct_btn.pack(side="left", padx=(14, 0))

        # Right: Debug toggle + points label
        right = tk.Frame(frame, bg=BG_MAIN)
        right.pack(side="right")

        self._debug_btn = tk.Button(
            right, text="Debug",
            font=("Segoe UI", 9), bg="#132213", fg="#6bcb77",
            activebackground="#6bcb77", activeforeground="#000000",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._toggle_debug,
        )
        self._debug_btn.pack(side="left", padx=(0, 10))

        self.points_label = tk.Label(
            right, text="Points: 0",
            font=("Segoe UI", 12), bg=BG_MAIN, fg=FG_HEADER,
        )
        self.points_label.pack(side="left")

        # Center: Reselect + Reset
        center = tk.Frame(frame, bg=BG_MAIN)
        center.pack(side="left", expand=True, fill="x")
        btn_group = tk.Frame(center, bg=BG_MAIN)
        btn_group.pack(anchor="center")
        tk.Button(
            btn_group, text="Reselect",
            font=("Segoe UI", 9), bg=BTN_NORMAL_BG, fg=FG_HEADER,
            activebackground="#1a4a8a", activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._reselect,
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            btn_group, text="Reset",
            font=("Segoe UI", 9), bg="#3a1a1a", fg="#ff6b6b",
            activebackground=ACCENT, activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._reset,
        ).pack(side="left")

    # ── Debug bar ──────────────────────────────────────────────────────────────

    def _build_debug_bar(self, parent):
        bar = tk.Frame(parent, bg=DEBUG_BAR_BG, pady=5)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_remove()
        self._debug_bar = bar

        tk.Label(bar, text="Debug:", bg=DEBUG_BAR_BG, fg="#6bcb77",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10, 8))

        self._link_btn = tk.Button(
            bar, text="Link",
            font=("Segoe UI", 9), bg=DEBUG_BAR_BG, fg="#e0e0e0",
            activebackground="#1a4a8a", activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
            command=self._toggle_link,
        )
        self._link_btn.pack(side="left", padx=(0, 4))

        self._type_btn = tk.Button(
            bar, text="Type",
            font=("Segoe UI", 9), bg=DEBUG_BAR_BG, fg="#e0e0e0",
            activebackground="#1a4a8a", activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
            command=self._toggle_type,
        )
        self._type_btn.pack(side="left", padx=(0, 4))

        self._stat_btn = tk.Button(
            bar, text="Stat",
            font=("Segoe UI", 9), bg=DEBUG_BAR_BG, fg="#e0e0e0",
            activebackground="#1a4a8a", activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
            command=self._toggle_stat,
        )
        self._stat_btn.pack(side="left", padx=(0, 4))

        tk.Label(bar, text="— right-click cancels selection",
                 bg=DEBUG_BAR_BG, fg="#555577",
                 font=("Segoe UI", 9, "italic")).pack(side="left", padx=(8, 0))

        if not self._source_file:
            tk.Label(bar, text="  ⚠ source file not found — changes will not persist",
                     bg=DEBUG_BAR_BG, fg=STATUS_ERROR,
                     font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _build_status_bar(self, parent):
        self.status_bar = tk.Label(
            parent, text="",
            font=("Segoe UI", 9, "italic"),
            bg=BG_MAIN, fg=STATUS_ERROR,
            anchor="w", padx=14, pady=4,
        )
        self.status_bar.grid(row=3, column=0, sticky="ew")

    def _set_status(self, message: str, error: bool = True):
        self.status_bar.config(text=message,
                               fg=STATUS_ERROR if error else STATUS_OK)
        if message:
            self.after(3000, lambda: self.status_bar.config(text=""))

    # ── Canvas renderer ────────────────────────────────────────────────────────

    def _build_canvas(self, parent):
        self._canvas = tk.Canvas(parent, bg=BG_MAIN, highlightthickness=0)
        self._canvas.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))

        self._col_label_items: dict[int, int] = {}
        self._col_lock_items:  dict[int, int] = {}
        self._node_oval_items: dict[str, int] = {}
        self._node_text_items: dict[str, int] = {}
        self._conn_lines: list[tuple[int, str, str]] = []
        self._tooltips: list[CanvasTooltip] = []

        # Connection lines first — lowest z-order
        for id1, id2 in self.tree.connections:
            lid = self._canvas.create_line(0, 0, 0, 0,
                                           fill=CONN_COLOR, width=2, tags="conn")
            self._conn_lines.append((lid, id1, id2))

        # Column labels + lock status text
        for col in range(COLUMN_COUNT):
            lbl = self._canvas.create_text(
                0, 0, text=str(COLUMN_LABELS[col]),
                font=("Segoe UI", 11, "bold"), fill=FG_HEADER)
            self._col_label_items[col] = lbl

            lck = self._canvas.create_text(
                0, 0, text="",
                font=("Segoe UI", 9, "italic"), fill=FG_LOCKED_TEXT)
            self._col_lock_items[col] = lck

        # Node circles — highest z-order
        for node in self.tree.nodes.values():
            pts, mx = node.current_points, node.max_points
            nid = node.id

            oval_id = self._canvas.create_oval(
                0, 0, 0, 0,
                fill=BTN_NORMAL_BG, outline=BTN_NORMAL_OUT, width=2,
                tags=("node", nid))
            text_id = self._canvas.create_text(
                0, 0, text=f"{pts}/{mx}",
                font=("Segoe UI", 10, "bold"), fill=BTN_NORMAL_FG,
                tags=("node", nid))

            self._node_oval_items[nid] = oval_id
            self._node_text_items[nid] = text_id

            self._canvas.tag_bind(nid, "<Button-1>",
                                  lambda e, n=nid: self._on_left_click(n, e))
            self._canvas.tag_bind(nid, "<Button-3>",
                                  lambda e, n=nid: self._on_right_click(n, e))
            self._canvas.tag_bind(nid, "<Enter>",
                                  lambda e: self._canvas.config(cursor="hand2"), add="+")
            self._canvas.tag_bind(nid, "<Leave>",
                                  lambda e: self._canvas.config(cursor=""), add="+")

            self._tooltips.append(
                CanvasTooltip(self._canvas, nid,
                              text_func=lambda n=nid: self._tooltip_text(n)))

        self._canvas.bind("<Configure>", self._on_canvas_resize)

    def _node_pos(self, node, cell_w: float, cell_h: float) -> tuple[float, float]:
        return (node.column * cell_w + cell_w / 2,
                HEADER_H + node.row * cell_h + cell_h / 2)

    def _on_canvas_resize(self, event):
        w, h = event.width, event.height
        if w <= 1 or h <= 1:
            return

        cell_w = w / COLUMN_COUNT
        cell_h = (h - HEADER_H) / ROW_COUNT
        R = NODE_R

        # Column labels and lock text
        for col in range(COLUMN_COUNT):
            cx = col * cell_w + cell_w / 2
            self._canvas.coords(self._col_label_items[col], cx, HEADER_H / 2 - 7)
            self._canvas.coords(self._col_lock_items[col],  cx, HEADER_H / 2 + 7)

        # Node circles
        for node in self.tree.nodes.values():
            x, y = self._node_pos(node, cell_w, cell_h)
            self._canvas.coords(self._node_oval_items[node.id],
                                x - R, y - R, x + R, y + R)
            self._canvas.coords(self._node_text_items[node.id], x, y)

        # Connection lines (endpoints offset to circle edge)
        for lid, id1, id2 in self._conn_lines:
            n1 = self.tree.nodes.get(id1)
            n2 = self.tree.nodes.get(id2)
            if not (n1 and n2):
                continue
            x1, y1 = self._node_pos(n1, cell_w, cell_h)
            x2, y2 = self._node_pos(n2, cell_w, cell_h)
            dx, dy = x2 - x1, y2 - y1
            dist = (dx ** 2 + dy ** 2) ** 0.5
            if dist:
                nx, ny = dx / dist * R, dy / dist * R
            else:
                nx = ny = 0
            self._canvas.coords(lid, x1 + nx, y1 + ny, x2 - nx, y2 - ny)

    # ── Tooltip ────────────────────────────────────────────────────────────────

    def _tooltip_text(self, node_id: str) -> str:
        node = self.tree.nodes.get(node_id)
        if node is None:
            return ""
        pts, mx = node.current_points, node.max_points
        lines = [f"{node.node_type.value}  {pts}/{mx}"]

        if not node.stats:
            lines.append("— No stats assigned —")
        else:
            if pts > 0:
                for s in node.stats:
                    lines.append(s.display(pts))
            if not node.is_full:
                if pts > 0:
                    lines.append("")          # blank line separator
                lines.append("Next level")
                for s in node.stats:
                    lines.append(s.display(pts + 1))

        return "\n".join(lines)

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _refresh(self):
        self.points_label.config(text=f"Points: {self.tree.total_points()}")

        for col in range(COLUMN_COUNT):
            unlocked = self.tree.is_column_unlocked(col)
            lck = self._col_lock_items[col]

            if unlocked:
                self._canvas.itemconfig(lck, text="", fill=FG_LOCKED_TEXT)
            else:
                needed = col * 3
                self._canvas.itemconfig(lck, text=f"Need {needed} pts", fill=STATUS_ERROR)

            for node in self.tree.nodes_in_column(col):
                oid = self._node_oval_items[node.id]
                tid = self._node_text_items[node.id]
                self._canvas.itemconfig(tid,
                                        text=f"{node.current_points}/{node.max_points}")
                if not unlocked:
                    self._canvas.itemconfig(oid, fill=BTN_LOCKED_BG, outline=BTN_LOCKED_OUT)
                    self._canvas.itemconfig(tid, fill=BTN_LOCKED_FG)
                elif node.is_full:
                    self._canvas.itemconfig(oid, fill=BTN_FULL_BG, outline=BTN_FULL_OUT)
                    self._canvas.itemconfig(tid, fill=BTN_FULL_FG)
                else:
                    self._canvas.itemconfig(oid, fill=BTN_NORMAL_BG, outline=BTN_NORMAL_OUT)
                    self._canvas.itemconfig(tid, fill=BTN_NORMAL_FG)

                # Re-apply link highlight after normal colours are set
                if self._link_first == node.id:
                    self._canvas.itemconfig(oid, outline=LINK_PENDING, width=3)

        for tt in self._tooltips:
            tt.refresh()

    # ── Click handlers ─────────────────────────────────────────────────────────

    def _on_left_click(self, node_id: str, event: tk.Event | None = None):
        if self._link_mode:
            self._handle_link_click(node_id)
            return
        if self._type_mode:
            self._handle_type_click(node_id, event)
            return
        if self._stat_mode:
            self._handle_stat_click(node_id)
            return
        try:
            self.tree.allocate(node_id)
            self._save()
            self._set_status("")
        except ValueError as e:
            self._set_status(str(e), error=True)
        self._refresh()

    def _on_right_click(self, node_id: str, event: tk.Event | None = None):
        if self._link_mode:
            self._cancel_link_selection()
            return
        if self._type_mode:
            return
        try:
            self.tree.deallocate(node_id)
            self._save()
            self._set_status("")
        except ValueError as e:
            self._set_status(str(e), error=True)
        self._refresh()

    def _reselect(self):
        trees = self.app.selected_trees
        slot = next((i for i, t in enumerate(trees) if t == self.tree.name), None)
        if slot is not None:
            if slot == 0:
                for i in range(4):
                    trees[i] = None
            else:
                trees[slot] = None
        self.app.show_tree_selector()

    def _reset(self):
        for node in self.tree.nodes.values():
            node.current_points = 0
        self._save()
        self._refresh()
        self._set_status("All points reset.", error=False)

    def _save(self):
        node_points = {nid: n.current_points for nid, n in self.tree.nodes.items()}
        core_talents = {str(s.threshold): s.selected_id
                        for s in self.tree.core_talent_slots}
        save_manager.save(self.tree.name, node_points, core_talents)

    # ── Core Talent overlay ────────────────────────────────────────────────────

    def _ct_btn_label(self) -> str:
        slots = self.tree.core_talent_slots
        if not slots:
            return "Core Talents"
        selected = sum(1 for s in slots if s.is_selected)
        return f"Core Talents ({selected}/{len(slots)})"

    def _update_ct_btn(self):
        self._ct_btn.config(text=self._ct_btn_label())

    def _open_core_talent_overlay(self):
        if hasattr(self, "_ct_overlay") and self._ct_overlay and self._ct_overlay.winfo_exists():
            self._dismiss_ct_overlay()
            return
        overlay = tk.Frame(self._canvas, bg="#06060f")
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()
        self._ct_overlay = overlay
        self._build_ct_overlay_content(overlay)
        self._bind_dismiss(overlay)

    def _dismiss_ct_overlay(self):
        if hasattr(self, "_ct_overlay") and self._ct_overlay and self._ct_overlay.winfo_exists():
            self._ct_overlay.destroy()
        self._ct_overlay = None

    def _bind_dismiss(self, widget):
        if not isinstance(widget, tk.Button):
            widget.bind("<Button-1>", lambda e: self._dismiss_ct_overlay(), add="+")
        for child in widget.winfo_children():
            self._bind_dismiss(child)

    def _build_ct_overlay_content(self, overlay: tk.Frame):
        total = self.tree.total_points()
        slots = self.tree.core_talent_slots

        card = tk.Frame(overlay, bg="#0d1527", relief="flat", bd=0)
        card.place(relx=0.5, rely=0.5, anchor="center")

        # Accent top border
        tk.Frame(card, bg=ACCENT, height=2).pack(fill="x")

        # Title
        tk.Label(card, text=f"Core Talents — {self.tree.name}",
                 font=("Segoe UI", 13, "bold"), bg="#0d1527", fg=ACCENT,
                 padx=24, pady=12).pack(anchor="w")

        if not slots:
            tk.Label(card, text="No core talents defined for this tree.",
                     font=("Segoe UI", 10), bg="#0d1527", fg=FG_LOCKED_TEXT,
                     padx=24, pady=8).pack()
        else:
            for slot in slots:
                unlocked = total >= slot.threshold
                self._build_ct_overlay_slot(card, slot, unlocked, total)

        # Dismiss hint
        tk.Label(card, text="Click anywhere outside to dismiss",
                 font=("Segoe UI", 8, "italic"), bg="#0d1527", fg="#444466",
                 pady=10).pack()

    def _build_ct_overlay_slot(self, card: tk.Frame, slot, unlocked: bool, total: int):
        # Slot header
        hdr = tk.Frame(card, bg="#0d1527")
        hdr.pack(fill="x", padx=24, pady=(6, 2))
        tk.Label(hdr, text=f"Threshold: {slot.threshold} pts",
                 font=("Segoe UI", 10, "bold"), bg="#0d1527", fg=FG_HEADER
                 ).pack(side="left")
        if unlocked:
            if slot.is_selected:
                status_text = f"  — {slot.selected_talent().name} selected"
                status_fg = STATUS_OK
            else:
                status_text = "  — choose one"
                status_fg = "#c084fc"
        else:
            status_text = f"  — need {slot.threshold - total} more pts"
            status_fg = FG_LOCKED_TEXT
        tk.Label(hdr, text=status_text, font=("Segoe UI", 9, "italic"),
                 bg="#0d1527", fg=status_fg).pack(side="left")

        tk.Frame(card, bg="#1e2040", height=1).pack(fill="x", padx=24, pady=(2, 6))

        # Option buttons
        opts = tk.Frame(card, bg="#0d1527")
        opts.pack(padx=24, pady=(0, 12))
        for talent in slot.options:
            is_sel = slot.selected_id == talent.id
            if not unlocked:
                bg, fg, border_col, state = BTN_LOCKED_BG, BTN_LOCKED_FG, BTN_LOCKED_OUT, "disabled"
            elif is_sel:
                bg, fg, border_col, state = BTN_FULL_BG, BTN_FULL_FG, ACCENT, "normal"
            else:
                bg, fg, border_col, state = BTN_NORMAL_BG, BTN_NORMAL_FG, "#2a2a5a", "normal"

            wrap = tk.Frame(opts, bg=border_col, padx=1, pady=1)
            wrap.pack(side="left", padx=(0, 10))
            tk.Button(
                wrap, text=talent.name,
                font=("Segoe UI", 10), width=12, height=2,
                bg=bg, fg=fg,
                activebackground="#1a4a8a", activeforeground="#ffffff",
                relief="flat", bd=0, state=state,
                command=lambda s=slot, t=talent: self._select_core_talent(s, t),
            ).pack()

    def _select_core_talent(self, slot, talent):
        if slot.selected_id == talent.id:
            slot.selected_id = None
        else:
            slot.selected_id = talent.id
        self._save()
        self._update_ct_btn()
        self._dismiss_ct_overlay()

    # ── Debug mode toggle ──────────────────────────────────────────────────────

    def _toggle_debug(self):
        self._debug_mode = not self._debug_mode
        if self._debug_mode:
            self._debug_bar.grid()
            self._debug_btn.config(relief="sunken", bg="#1a3a1a")
        else:
            self._debug_bar.grid_remove()
            self._debug_btn.config(relief="flat", bg="#132213")
            self._exit_link_mode()
            self._exit_type_mode()
            self._exit_stat_mode()

    def _toggle_link(self):
        if self._link_mode:
            self._exit_link_mode()
            self._set_status("")
        else:
            self._exit_type_mode()
            self._link_mode = True
            self._link_btn.config(relief="sunken", bg="#0f3460")
            self._set_status("Link: click the first node", error=False)

    def _toggle_type(self):
        if self._type_mode:
            self._exit_type_mode()
            self._set_status("")
        else:
            self._exit_link_mode()
            self._type_mode = True
            self._type_btn.config(relief="sunken", bg="#0f3460")
            self._set_status("Type: click any node to change its type", error=False)

    def _exit_link_mode(self):
        if self._link_first is not None:
            oid = self._node_oval_items.get(self._link_first)
            if oid:
                self._canvas.itemconfig(oid, outline=BTN_NORMAL_OUT, width=2)
            self._link_first = None
        self._link_mode = False
        if hasattr(self, "_link_btn"):
            self._link_btn.config(relief="flat", bg=DEBUG_BAR_BG)

    def _exit_type_mode(self):
        self._type_mode = False
        if hasattr(self, "_type_btn"):
            self._type_btn.config(relief="flat", bg=DEBUG_BAR_BG)

    def _toggle_stat(self):
        if self._stat_mode:
            self._exit_stat_mode()
            self._set_status("")
        else:
            self._exit_link_mode()
            self._exit_type_mode()
            self._stat_mode = True
            self._stat_btn.config(relief="sunken", bg="#0f3460")
            self._set_status("Stat: click any node to assign its stats", error=False)

    def _exit_stat_mode(self):
        self._stat_mode = False
        if hasattr(self, "_stat_btn"):
            self._stat_btn.config(relief="flat", bg=DEBUG_BAR_BG)

    def _cancel_link_selection(self):
        """Clear the pending first-node selection but stay in link mode."""
        if self._link_first is not None:
            oid = self._node_oval_items.get(self._link_first)
            if oid:
                self._canvas.itemconfig(oid, outline=BTN_NORMAL_OUT, width=2)
            self._link_first = None
        self._set_status("Link: selection cleared — click the first node", error=False)

    # ── Link handling ──────────────────────────────────────────────────────────

    def _handle_link_click(self, node_id: str):
        if self._link_first is None:
            # First node selected — highlight it
            self._link_first = node_id
            self._canvas.itemconfig(self._node_oval_items[node_id],
                                    outline=LINK_PENDING, width=3)
            self._set_status("Link: now click the second node", error=False)
        elif self._link_first == node_id:
            # Same node clicked twice — cancel selection
            self._cancel_link_selection()
        else:
            id1, id2 = self._link_first, node_id
            # Restore first-node outline
            self._canvas.itemconfig(self._node_oval_items[id1],
                                    outline=BTN_NORMAL_OUT, width=2)
            self._link_first = None

            # Determine stored order (connection may be (id1,id2) or (id2,id1))
            if (id1, id2) in self.tree.connections:
                stored = (id1, id2)
            elif (id2, id1) in self.tree.connections:
                stored = (id2, id1)
            else:
                stored = None

            if stored is not None:
                # Already linked — remove it
                self.tree.connections.remove(stored)
                self._remove_connection_from_canvas(stored[0], stored[1])
                if self._source_file:
                    try:
                        self._remove_connection_from_file(stored[0], stored[1])
                        self._set_status(f"Unlinked {stored[0]} ↔ {stored[1]} and saved.", error=False)
                    except Exception as exc:
                        self._set_status(f"Unlinked in memory; file write failed: {exc}", error=True)
                else:
                    self._set_status(f"Unlinked {stored[0]} ↔ {stored[1]} (not persisted).", error=True)
            else:
                # Not linked — create connection
                self.tree.add_connection(id1, id2)
                self._add_connection_to_canvas(id1, id2)
                if self._source_file:
                    try:
                        self._write_connection_to_file(id1, id2)
                        self._set_status(f"Linked {id1} → {id2} and saved to file.", error=False)
                    except Exception as exc:
                        self._set_status(f"Linked in memory; file write failed: {exc}", error=True)
                else:
                    self._set_status(f"Linked {id1} → {id2} (no source file — not persisted).", error=True)

    def _add_connection_to_canvas(self, id1: str, id2: str):
        lid = self._canvas.create_line(0, 0, 0, 0, fill=CONN_COLOR, width=2, tags="conn")
        self._canvas.tag_lower(lid, "node")
        self._conn_lines.append((lid, id1, id2))
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w > 1 and h > 1:
            cell_w = w / COLUMN_COUNT
            cell_h = (h - HEADER_H) / ROW_COUNT
            n1 = self.tree.nodes.get(id1)
            n2 = self.tree.nodes.get(id2)
            if n1 and n2:
                x1, y1 = self._node_pos(n1, cell_w, cell_h)
                x2, y2 = self._node_pos(n2, cell_w, cell_h)
                dx, dy = x2 - x1, y2 - y1
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist:
                    nx, ny = dx / dist * NODE_R, dy / dist * NODE_R
                else:
                    nx = ny = 0
                self._canvas.coords(lid, x1 + nx, y1 + ny, x2 - nx, y2 - ny)

    def _remove_connection_from_canvas(self, id1: str, id2: str):
        for entry in self._conn_lines:
            lid, a, b = entry
            if (a == id1 and b == id2) or (a == id2 and b == id1):
                self._canvas.delete(lid)
                self._conn_lines.remove(entry)
                break

    # ── Type handling ──────────────────────────────────────────────────────────

    def _handle_type_click(self, node_id: str, event: tk.Event | None):
        node = self.tree.nodes.get(node_id)
        if node is None or event is None:
            return

        menu = tk.Menu(self, tearoff=0,
                       bg="#1a1a2e", fg="#e0e0e0",
                       activebackground="#0f3460", activeforeground="#ffffff",
                       font=("Segoe UI", 9))

        for nt in NodeType:
            indicator = "→ " if nt == node.node_type else "   "
            menu.add_command(
                label=f"{indicator}{nt.value}",
                command=lambda t=nt: self._change_node_type(node_id, t),
            )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _change_node_type(self, node_id: str, new_type: NodeType):
        node = self.tree.nodes.get(node_id)
        if node is None or node.node_type == new_type:
            return

        new_max = 1 if new_type == NodeType.LEGENDARY_MEDIUM else 3
        node.node_type = new_type
        node.max_points = new_max
        if node.current_points > new_max:
            node.current_points = new_max

        if self._source_file:
            try:
                self._write_node_type_to_file(node_id, new_type, new_max)
                self._set_status(f"Changed {node_id} → {new_type.value} and saved.", error=False)
            except Exception as exc:
                self._set_status(f"Changed in memory; file write failed: {exc}", error=True)
        else:
            self._set_status(f"Changed {node_id} → {new_type.value} (not persisted).", error=True)

        self._refresh()

    # ── Stat handling ─────────────────────────────────────────────────────────

    def _handle_stat_click(self, node_id: str):
        node = self.tree.nodes.get(node_id)
        if node is None:
            return
        self._open_stat_editor(node)

    def _open_stat_editor(self, node):
        if hasattr(self, "_stat_overlay") and self._stat_overlay and \
                self._stat_overlay.winfo_exists():
            self._stat_overlay.destroy()

        ranks = node.max_points
        working_stats: list[NodeStat] = list(node.stats)

        # Build pool lookups
        pool_by_cat: dict[str, list] = {}
        all_pool_stats: list = []
        for stat_key, mod_def in NODE_MODIFIER_POOL.items():
            meta = STAT_META.get(stat_key)
            if not meta:
                continue
            entry = (meta.display_name, stat_key, mod_def)
            pool_by_cat.setdefault(meta.category, []).append(entry)
            all_pool_stats.append(entry)
        all_pool_stats.sort(key=lambda x: x[0])
        categories = [c for c in CATEGORIES if c in pool_by_cat]

        # ── Overlay (full-canvas dark backdrop) ───────────────────────────────
        overlay = tk.Frame(self._canvas, bg="#06060f")
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()
        self._stat_overlay = overlay

        card = tk.Frame(overlay, bg="#0d1527", relief="flat", bd=0)
        card.place(relx=0.5, rely=0.5, anchor="center")

        def cancel():
            overlay.destroy()
            self._stat_overlay = None

        def maybe_dismiss(event):
            cx, cy = card.winfo_rootx(), card.winfo_rooty()
            cw, ch = card.winfo_width(), card.winfo_height()
            if not (cx <= event.x_root < cx + cw and
                    cy <= event.y_root < cy + ch):
                cancel()

        overlay.bind("<Button-1>", maybe_dismiss)

        # ── Card title ────────────────────────────────────────────────────────
        tk.Frame(card, bg=ACCENT, height=2).pack(fill="x")
        rank_label = f"{ranks} rank{'s' if ranks > 1 else ''}"
        tk.Label(card,
                 text=f"Node Stats — {node.id}  ·  "
                      f"{node.node_type.value}  ({rank_label})",
                 font=("Segoe UI", 12, "bold"),
                 bg="#0d1527", fg=ACCENT, padx=20, pady=10).pack(anchor="w")

        # ── Main panels ───────────────────────────────────────────────────────
        main = tk.Frame(card, bg="#0d1527")
        main.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Left: current stats ─────────────────────────────────────────────────
        left = tk.Frame(main, bg="#0d1527", width=230, height=360)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="Current Stats",
                 font=("Segoe UI", 10, "bold"),
                 bg="#0d1527", fg=FG_HEADER).pack(anchor="w", pady=(0, 6))

        stats_frame = tk.Frame(left, bg="#0d1527")
        stats_frame.pack(fill="both", expand=True)

        def refresh_stats_list():
            for w in stats_frame.winfo_children():
                w.destroy()
            if not working_stats:
                tk.Label(stats_frame, text="— No stats assigned —",
                         font=("Segoe UI", 9, "italic"),
                         bg="#0d1527", fg=FG_LOCKED_TEXT,
                         wraplength=200, anchor="w").pack(anchor="w")
                return
            for i, ns in enumerate(working_stats):
                meta = STAT_META.get(ns.stat)
                name = meta.display_name if meta else ns.stat.value
                unit = meta.unit if meta else ""
                if ns.values:
                    inc = ns.values[0]
                    fmt = lambda v: (f"+{v*100:.0f}%" if unit == "%" else
                                     f"+{v:.0f}" if v == int(v) else f"+{v:.1f}")
                    if ranks > 1:
                        sub = "  /  ".join(fmt(v) for v in ns.values)
                    else:
                        sub = fmt(inc)
                else:
                    sub = ""

                row_f = tk.Frame(stats_frame, bg="#111830", padx=6, pady=4)
                row_f.pack(fill="x", pady=2)

                def _make_remove(idx):
                    def _remove():
                        working_stats.pop(idx)
                        refresh_stats_list()
                    return _remove

                tk.Button(row_f, text="✕", font=("Segoe UI", 8),
                          bg="#3a1a1a", fg=ACCENT, relief="flat", bd=0,
                          cursor="hand2", width=2,
                          command=_make_remove(i)).pack(side="right",
                                                        padx=(4, 0))
                tk.Label(row_f, text=name,
                         font=("Segoe UI", 9, "bold"),
                         bg="#111830", fg=BTN_FULL_FG,
                         wraplength=160, anchor="w",
                         justify="left").pack(anchor="w")
                if sub:
                    tk.Label(row_f, text=sub, font=("Segoe UI", 7),
                             bg="#111830", fg=FG_HEADER,
                             wraplength=160, anchor="w",
                             justify="left").pack(anchor="w")

        refresh_stats_list()

        tk.Frame(main, bg="#1e2040", width=1).pack(side="left", fill="y",
                                                    padx=(0, 10))

        # Right: add stat ─────────────────────────────────────────────────────
        right = tk.Frame(main, bg="#0d1527", width=290, height=360)
        right.pack(side="left", fill="y")
        right.pack_propagate(False)

        tk.Label(right, text="Add Stat",
                 font=("Segoe UI", 10, "bold"),
                 bg="#0d1527", fg=FG_HEADER).pack(anchor="w", pady=(0, 6))

        # Search
        sf = tk.Frame(right, bg="#0d1527")
        sf.pack(fill="x", pady=(0, 4))
        tk.Label(sf, text="Search:", font=("Segoe UI", 9),
                 bg="#0d1527", fg=FG_HEADER).pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(sf, textvariable=search_var, font=("Segoe UI", 9),
                 bg="#0f1e35", fg=FG_HEADER, insertbackground=FG_HEADER,
                 relief="flat", width=22).pack(side="left", padx=(6, 0))

        # Category
        cf = tk.Frame(right, bg="#0d1527")
        cf.pack(fill="x", pady=(0, 4))
        tk.Label(cf, text="Category:", font=("Segoe UI", 9),
                 bg="#0d1527", fg=FG_HEADER).pack(side="left")
        cat_var = tk.StringVar(value=categories[0] if categories else "")
        cat_menu = tk.OptionMenu(cf, cat_var, *categories)
        cat_menu.config(font=("Segoe UI", 9), bg="#0f3460", fg=FG_HEADER,
                        activebackground="#1a4a8a", highlightthickness=0,
                        relief="flat")
        cat_menu["menu"].config(bg="#0f3460", fg=FG_HEADER,
                                font=("Segoe UI", 9))
        cat_menu.pack(side="left", padx=(6, 0))

        # Stat listbox
        lf = tk.Frame(right, bg="#0d1527")
        lf.pack(fill="x", pady=(0, 8))
        stat_lb = tk.Listbox(lf, font=("Segoe UI", 9),
                             bg="#0f1e35", fg=FG_HEADER,
                             selectbackground="#0f3460",
                             selectforeground="#ffffff",
                             height=9, width=36, relief="flat", bd=0)
        lb_scroll = tk.Scrollbar(lf, orient="vertical", command=stat_lb.yview)
        stat_lb.config(yscrollcommand=lb_scroll.set)
        stat_lb.pack(side="left")
        lb_scroll.pack(side="right", fill="y")

        current_stat_refs: list = []

        def populate_stat_list(*_):
            query = search_var.get().strip().lower()
            stat_lb.delete(0, "end")
            current_stat_refs.clear()
            if query:
                for display, sk, md in all_pool_stats:
                    if query in display.lower():
                        stat_lb.insert("end", display)
                        current_stat_refs.append((sk, md))
            else:
                for display, sk, md in pool_by_cat.get(cat_var.get(), []):
                    stat_lb.insert("end", display)
                    current_stat_refs.append((sk, md))

        search_var.trace_add("write", populate_stat_list)
        cat_var.trace_add("write", populate_stat_list)
        populate_stat_list()

        # Rank increment
        inc_row = tk.Frame(right, bg="#0d1527")
        inc_row.pack(fill="x", pady=(0, 8))
        inc_label = "Value" if ranks == 1 else "Rank Increment"
        tk.Label(inc_row, text=f"{inc_label}:", font=("Segoe UI", 9),
                 bg="#0d1527", fg=FG_HEADER).pack(side="left")
        increment_entry = tk.Entry(inc_row, font=("Segoe UI", 9),
                                   bg="#0f1e35", fg=FG_HEADER,
                                   insertbackground=FG_HEADER,
                                   width=10, relief="flat")
        increment_entry.pack(side="left", padx=(8, 0))

        def on_stat_select(_event=None):
            sel = stat_lb.curselection()
            if not sel:
                return
            _, mod_def = current_stat_refs[sel[0]]
            if node.node_type == NodeType.LEGENDARY_MEDIUM:
                step = mod_def.legendary_increment
            elif node.node_type == NodeType.MEDIUM:
                step = mod_def.medium_increment
            else:
                step = mod_def.micro_increment
            increment_entry.delete(0, "end")
            increment_entry.insert(0, str(round(step, 6)))

        stat_lb.bind("<<ListboxSelect>>", on_stat_select)

        def add_stat():
            sel = stat_lb.curselection()
            if not sel:
                self._set_status("Select a stat from the list first.",
                                 error=True)
                return
            stat_key, _ = current_stat_refs[sel[0]]
            try:
                step = float(increment_entry.get())
            except ValueError:
                self._set_status("Rank Increment must be a number.", error=True)
                return
            if node.node_type == NodeType.LEGENDARY_MEDIUM:
                values = [step]
            else:
                values = [round(step * (r + 1), 8) for r in range(ranks)]
            working_stats.append(NodeStat(stat_key, values))
            refresh_stats_list()
            self._set_status("")

        tk.Button(right, text="Add Stat",
                  font=("Segoe UI", 9), bg=BTN_NORMAL_BG, fg=FG_HEADER,
                  activebackground="#1a4a8a", activeforeground="#ffffff",
                  relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                  command=add_stat).pack(anchor="w")

        # ── Bottom buttons ────────────────────────────────────────────────────
        tk.Frame(card, bg=ACCENT, height=1).pack(fill="x")
        btn_frame = tk.Frame(card, bg="#0d1527", pady=10)
        btn_frame.pack(fill="x", padx=20)

        def save():
            node.stats = working_stats
            self._save_node_stats(node)
            self._refresh()
            self._set_status(f"Stats saved for {node.id}.", error=False)
            overlay.destroy()
            self._stat_overlay = None

        tk.Button(btn_frame, text="Save",
                  font=("Segoe UI", 9), bg="#132213", fg="#6bcb77",
                  activebackground="#6bcb77", activeforeground="#000000",
                  relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                  command=save).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Cancel",
                  font=("Segoe UI", 9), bg="#3a1a1a", fg="#ff6b6b",
                  activebackground=ACCENT, activeforeground="#ffffff",
                  relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                  command=cancel).pack(side="left")
        tk.Label(btn_frame, text="Click outside to cancel",
                 font=("Segoe UI", 9, "italic"),
                 bg="#0d1527", fg="#444466").pack(side="left", padx=(16, 0))

    def _save_node_stats(self, node):
        node_stats_manager.save_node(self.tree.name, node.id, node.stats)

    def _load_node_stats(self):
        data = node_stats_manager.load()
        tree_data = data.get(self.tree.name, {})
        for node_id, stat_list in tree_data.items():
            node = self.tree.nodes.get(node_id)
            if node is None:
                continue
            node.stats = []
            for s in stat_list:
                try:
                    node.stats.append(NodeStat(Stat(s["stat"]), s["values"]))
                except (ValueError, KeyError):
                    pass

    # ── File persistence ───────────────────────────────────────────────────────

    def _write_connection_to_file(self, id1: str, id2: str):
        with open(self._source_file, "r", encoding="utf-8") as f:
            content = f.read()
        if "    return tree" not in content:
            raise ValueError("'return tree' not found in source file")
        insert = f'    tree.add_connection("{id1}", "{id2}")\n'
        content = content.replace("    return tree", insert + "    return tree", 1)
        with open(self._source_file, "w", encoding="utf-8") as f:
            f.write(content)

    def _remove_connection_from_file(self, id1: str, id2: str):
        with open(self._source_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Match either order
        patterns = [
            f'tree.add_connection("{id1}", "{id2}")',
            f'tree.add_connection("{id2}", "{id1}")',
        ]
        new_lines = [l for l in lines if not any(p in l for p in patterns)]
        if len(new_lines) == len(lines):
            raise ValueError(f"Connection {id1} ↔ {id2} not found in source file")
        with open(self._source_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def _write_node_type_to_file(self, node_id: str, new_type: NodeType, new_max: int):
        with open(self._source_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if f'id="{node_id}"' in line:
                line = re.sub(r"node_type=NodeType\.\w+",
                              f"node_type=NodeType.{new_type.name}", line)
                line = re.sub(r"max_points=\d+", f"max_points={new_max}", line)
                lines[i] = line
                break
        else:
            raise ValueError(f"Node '{node_id}' not found in source file")
        with open(self._source_file, "w", encoding="utf-8") as f:
            f.writelines(lines)
