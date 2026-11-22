"""The Neighbours tab: roster list, add/edit form, archive/restore/delete and per-neighbour detail."""
from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk

from .db import ValidationError
from .models import MODE_CUMULATIVE, Neighbour
from .scoring import COUNTERS, DERBY, LEVELS, SHORT_LABELS, neighbour_history
from .ui_common import C, FONT, ScrollFrame, make_card
from .ui_dialogs import BulkAddDialog
from .ui_monday import rank_sort_key
from .util import fmt_date, fmt_int, fmt_period, fmt_score, fmt_signed

RANK_CHOICES = ("Leader", "Elder", "Member")


class NeighboursTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(20, 14, 20, 12))
        self.app = app
        self.ds = None
        self.current_id: int | None = None
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        scroller = ScrollFrame(self, background=C["bg"], inner_style="TFrame")
        scroller.pack(fill="both", expand=True)
        page = scroller.inner
        ttk.Label(page, text="Neighbours", style="Title.TLabel").pack(anchor="w")
        ttk.Label(page, text="Each neighbour keeps one internal ID, so renaming them or changing their rank "
                             "never loses their history.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        panes = ttk.Frame(page)
        panes.pack(fill="both", expand=True)
        panes.columnconfigure(1, weight=1)
        panes.rowconfigure(0, weight=1)
        left = ttk.Frame(panes, padding=(0, 0, 14, 0))
        right = ttk.Frame(panes)
        left.grid(row=0, column=0, sticky="ns")
        right.grid(row=0, column=1, sticky="nsew")
        self._build_list(left)
        self._build_detail(right)

    def _build_list(self, parent) -> None:
        search = ttk.Frame(parent)
        search.pack(fill="x")
        ttk.Label(search, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        self.search_var.trace_add("write", lambda *_: self.refresh_list())
        self.show_archived = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Show archived neighbours", variable=self.show_archived,
                        command=self.refresh_list).pack(anchor="w", pady=(6, 6))

        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True)
        cols = ("name", "rank", "level", "status")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="browse", height=12)
        for col, text, width, anchor in (("name", "Farm name", 130, "w"), ("rank", "In-game rank", 100, "w"),
                                         ("level", "Level", 54, "e"), ("status", "Status", 66, "w")):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor, stretch=col == "name")
        scroll = ttk.Scrollbar(box, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.tag_configure("archived", foreground=C["muted"])
        self.tree.bind("<<TreeviewSelect>>", self._selected)

        self.count_label = ttk.Label(parent, text="", style="Small.TLabel")
        self.count_label.pack(anchor="w", pady=(6, 6))
        row1 = ttk.Frame(parent)
        row1.pack(fill="x")
        ttk.Button(row1, text="Add neighbour", style="Primary.TButton", command=self.new_mode).pack(side="left")
        ttk.Button(row1, text="Add several…", command=self.add_several).pack(side="left", padx=8)
        row2 = ttk.Frame(parent)
        row2.pack(fill="x", pady=(8, 0))
        self.archive_button = ttk.Button(row2, text="Archive", command=self.toggle_archive)
        self.archive_button.pack(side="left")
        self.delete_button = ttk.Button(row2, text="Delete permanently…", style="Danger.TButton",
                                        command=self.delete)
        self.delete_button.pack(side="left", padx=8)

    def _build_detail(self, parent) -> None:
        outer, card = make_card(parent, padding=16)
        outer.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=1)
        self.heading = ttk.Label(card, text="", style="CardHeading.TLabel", font=(FONT, 15, "bold"))
        self.heading.grid(row=0, column=0, columnspan=3, sticky="w")
        self.subheading = ttk.Label(card, text="", style="CardMuted.TLabel")
        self.subheading.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.name_var, self.rank_var, self.tag_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(card, text="Farm name", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(card, textvariable=self.name_var).grid(row=2, column=1, sticky="ew", padx=10, pady=3)
        ttk.Label(card, text="In-game rank", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(card, textvariable=self.rank_var, values=RANK_CHOICES, width=18
                     ).grid(row=3, column=1, sticky="w", padx=10, pady=3)
        self.rank_hint = ttk.Label(card, text="Their in-game role (Leader, Elder, Member) or position in the in-game "
                                              "list. Leaderboard position is worked out on the Rankings tab.",
                                   style="CardMuted.TLabel", font=(FONT, 9), wraplength=340, justify="left")
        self.rank_hint.grid(row=4, column=1, columnspan=2, sticky="w", padx=10)
        ttk.Label(card, text="Player tag", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=3)
        tag_row = ttk.Frame(card, style="Card.TFrame")
        tag_row.grid(row=5, column=1, columnspan=2, sticky="w", padx=10, pady=3)
        ttk.Entry(tag_row, textvariable=self.tag_var, width=22).pack(side="left")
        ttk.Label(tag_row, text="  optional", style="CardMuted.TLabel", font=(FONT, 9)).pack(side="left")
        ttk.Label(card, text="Notes", style="Card.TLabel").grid(row=6, column=0, sticky="nw", pady=3)
        self.notes = tk.Text(card, height=3, width=10, font=(FONT, 10), relief="solid", borderwidth=1,
                             padx=6, pady=4, bg=C["entry"], highlightthickness=0, wrap="word")
        self.notes.grid(row=6, column=1, columnspan=2, sticky="ew", padx=10, pady=3)
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 10))
        self.save_button = ttk.Button(actions, text="Save changes", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="left")
        self.revert_button = ttk.Button(actions, text="Revert", command=self._reload_form)
        self.revert_button.pack(side="left", padx=8)
        self.form_message = ttk.Label(actions, text="", style="CardGood.TLabel")
        self.form_message.pack(side="left", padx=8)

        self.detail = ttk.Frame(card, style="Card.TFrame")
        self.detail.grid(row=8, column=0, columnspan=3, sticky="nsew")
        card.rowconfigure(8, weight=1)
        self.detail.columnconfigure(0, weight=1)
        self.detail.rowconfigure(4, weight=1)

        ttk.Label(self.detail, text="Latest stats", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        self.stats_note = ttk.Label(self.detail, text="", style="CardMuted.TLabel")
        self.stats_note.grid(row=1, column=0, sticky="w")
        cols = ("measure", "latest", "previous", "change", "counts")
        self.stats = ttk.Treeview(self.detail, columns=cols, show="headings", height=5, selectmode="none")
        for col, text, width, anchor in (("measure", "Measure", 120, "w"), ("latest", "Latest", 70, "e"),
                                         ("previous", "Previous", 80, "e"), ("change", "Change", 70, "e"),
                                         ("counts", "Counts as this week", 170, "w")):
            self.stats.heading(col, text=text, anchor=anchor)
            self.stats.column(col, width=width, anchor=anchor)
        self.stats.grid(row=2, column=0, sticky="ew", pady=(4, 10))

        self.history_title = ttk.Label(self.detail, text="History (double-click a week to open it in Monday Update)",
                                       style="CardHeading.TLabel")
        self.history_title.grid(row=3, column=0, sticky="nw")
        hist_box = ttk.Frame(self.detail, style="Card.TFrame")
        hist_box.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        hist_box.columnconfigure(0, weight=1)
        hist_box.rowconfigure(0, weight=1)
        hcols = ("week", "level", "nurture", "donations", "derby", "gain", "npts", "dpts", "derby_pts", "score", "pos")
        self.history = ttk.Treeview(hist_box, columns=hcols, show="headings", height=6, selectmode="browse")
        for col, text, width, anchor in (
                ("week", "Week (Monday)", 120, "w"), ("level", "Level", 48, "e"), ("nurture", "Nurture", 70, "e"),
                ("donations", "Donations", 78, "e"), ("derby", "Derby", 58, "e"), ("gain", "Levels +", 70, "e"),
                ("npts", "Nurture +", 82, "e"), ("dpts", "Donations +", 94, "e"), ("derby_pts", "Derby +", 70, "e"),
                ("score", "Score", 56, "e"), ("pos", "Pos.", 44, "e")):
            self.history.heading(col, text=text, anchor=anchor)
            self.history.column(col, width=width, anchor=anchor, stretch=False)
        vscroll = ttk.Scrollbar(hist_box, command=self.history.yview)
        hscroll = ttk.Scrollbar(hist_box, orient="horizontal", command=self.history.xview)
        self.history.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.history.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        self.history.bind("<Double-1>", self._open_week)
        self.history.tag_configure("warn", foreground=C["warn"])

    # ------------------------------------------------------------------- list
    def refresh(self) -> None:
        self.ds = self.app.db.load_dataset()
        self.refresh_list()
        if self.current_id is not None and self.current_id not in self.ds.neighbours:
            self.current_id = None
        self._reload_form()

    def refresh_list(self) -> None:
        if self.ds is None:
            return
        needle = self.search_var.get().strip().lower()
        latest_level: dict[int, int] = {}
        for week in sorted(self.ds.entries):
            for nid, e in self.ds.entries[week].items():
                if e.farm_level is not None:
                    latest_level[nid] = e.farm_level
        people = sorted((n for n in self.ds.neighbours.values()
                         if (self.show_archived.get() or not n.archived)
                         and (not needle or needle in f"{n.farm_name} {n.game_rank} {n.player_tag} {n.notes}".lower())),
                        key=rank_sort_key)
        self.tree.delete(*self.tree.get_children())
        for n in people:
            self.tree.insert("", "end", iid=str(n.id), tags=("archived",) if n.archived else (),
                             values=(n.farm_name, n.game_rank or "—", fmt_int(latest_level.get(n.id)),
                                     "Archived" if n.archived else "Active"))
        active = sum(1 for n in self.ds.neighbours.values() if not n.archived)
        archived = len(self.ds.neighbours) - active
        self.count_label.configure(text=f"{active} active" + (f", {archived} archived" if archived else "") +
                                        (f"  ·  showing {len(people)}" if needle else ""))
        if self.current_id is not None and self.tree.exists(str(self.current_id)):
            self.tree.selection_set(str(self.current_id))
            self.tree.see(str(self.current_id))
        self._update_buttons()

    def _selected(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        nid = int(sel[0])
        if nid != self.current_id:
            self.current_id = nid
            self._reload_form()

    def _update_buttons(self) -> None:
        n = self.ds.neighbours.get(self.current_id) if self.ds and self.current_id is not None else None
        state = "normal" if n else "disabled"
        self.archive_button.configure(state=state, text="Restore" if n and n.archived else "Archive")
        self.delete_button.configure(state=state)

    # ------------------------------------------------------------------- form
    def new_mode(self) -> None:
        self.current_id = None
        self.tree.selection_remove(*self.tree.selection())
        self._reload_form()
        self.name_entry_focus()

    def name_entry_focus(self) -> None:
        for child in self.heading.master.grid_slaves(row=2, column=1):
            child.focus_set()

    def _reload_form(self) -> None:
        n = self.ds.neighbours.get(self.current_id) if self.ds and self.current_id is not None else None
        self.form_message.configure(text="")
        if n is None:
            self.heading.configure(text="New neighbour")
            self.subheading.configure(text="Fill in the details and press Add neighbour.")
            self.name_var.set("")
            self.rank_var.set("")
            self.tag_var.set("")
            self.notes.delete("1.0", "end")
            self.save_button.configure(text="Add neighbour")
            self.revert_button.configure(state="disabled")
            self.detail.grid_remove()
        else:
            self.heading.configure(text=n.farm_name)
            self.subheading.configure(text=("Archived on " + fmt_date(n.archived_on) + ". Hidden from new weekly updates; "
                                            "history is kept.") if n.archived else
                                      "Active. Appears in every new weekly update.")
            self.name_var.set(n.farm_name)
            self.rank_var.set(n.game_rank)
            self.tag_var.set(n.player_tag)
            self.notes.delete("1.0", "end")
            self.notes.insert("1.0", n.notes)
            self.save_button.configure(text="Save changes")
            self.revert_button.configure(state="normal")
            self.detail.grid()
            self._fill_detail(n)
        self._update_buttons()

    # ----------------------------------------------------------------- detail
    def _fill_detail(self, n: Neighbour) -> None:
        settings = self.app.settings
        history = neighbour_history(self.ds, n.id, settings)
        for tree in (self.stats, self.history):
            tree.delete(*tree.get_children())
        if not history:
            self.stats_note.configure(text="No weekly entries yet for this neighbour.")
            return
        latest = history[0]
        self.stats_note.configure(
            text=f"Week of {fmt_date(latest.week)} (reporting period {fmt_period(latest.week)})")
        cur, prev = latest.entry, latest.previous_entry
        prev_result = next((h for h in history if h.week == latest.week - timedelta(days=7)), None)

        def change(a, b):
            return fmt_signed(a - b) if a is not None and b is not None else "—"

        m = latest.metrics
        cumulative = {k: getattr(settings, f"{k}_mode") == MODE_CUMULATIVE for k in COUNTERS}
        nouns = {"nurture": "points earned", "donations": "made", "derby": "points earned"}
        rows = [("Farm level", fmt_int(cur.farm_level), fmt_int(prev.farm_level if prev else None),
                 change(cur.farm_level, prev.farm_level if prev else None),
                 f"{m[LEVELS].text} levels gained" if m[LEVELS].usable else m[LEVELS].text)]
        for key in COUNTERS:
            label = SHORT_LABELS[key]
            now, before = getattr(cur, key), getattr(prev, key) if prev else None
            tag = " (total)" if cumulative[key] else " (weekly)"
            noun = nouns[key]
            rows.append((label + tag, fmt_int(now), fmt_int(before) if cumulative[key] else "—",
                         change(now, before) if cumulative[key] else "—",
                         f"{m[key].text} {noun}" if m[key].usable else m[key].text))
        prev_score = prev_result.score if prev_result else None
        rows.append(("Overall score", fmt_score(latest.score), fmt_score(prev_score) if prev_result else "—",
                     change(latest.score, prev_score) if latest.score is not None and prev_score is not None else "—",
                     f"Leaderboard position {latest.position}" if latest.position else "No leaderboard position"))
        for row in rows:
            self.stats.insert("", "end", values=row)

        for h in history:
            e = h.entry
            self.history.insert("", "end", iid=h.week.isoformat(),
                                tags=("warn",) if h.flags_text else (),
                                values=(fmt_date(h.week), fmt_int(e.farm_level), fmt_int(e.nurture), fmt_int(e.donations),
                                        fmt_int(e.derby), h.metrics[LEVELS].text, h.metrics["nurture"].text,
                                        h.metrics["donations"].text, h.metrics[DERBY].text,
                                        "—" if h.score is None else f"{h.score:.2f}",
                                        fmt_int(h.position)))

    def _open_week(self, _event=None) -> None:
        sel = self.history.selection()
        if sel:
            self.app.open_week_in_monday(date.fromisoformat(sel[0]))

    # ---------------------------------------------------------------- actions
    def _form_values(self):
        return (self.name_var.get(), self.rank_var.get(), self.tag_var.get(), self.notes.get("1.0", "end"))

    def save(self) -> None:
        name, rank, tag, notes = self._form_values()
        try:
            if self.current_id is None:
                if self.app.db.name_in_use(name) and not messagebox.askyesno(
                        "Name already used", f"A neighbour called “{name.strip()}” already exists. "
                        "Add another one with the same name?", icon="warning", default="no", parent=self):
                    return
                self.current_id = self.app.db.add_neighbour(name, rank, tag, notes)
                message = "Added ✓"
            else:
                if self.app.db.name_in_use(name, self.current_id) and not messagebox.askyesno(
                        "Name already used", f"Another neighbour is already called “{name.strip()}”. "
                        "Use the same name anyway?", icon="warning", default="no", parent=self):
                    return
                self.app.db.update_neighbour(self.current_id, name, rank, tag, notes)
                message = "Saved ✓ (history kept)"
        except ValidationError as exc:
            messagebox.showwarning("Check the details", str(exc), parent=self)
            return
        self.app.neighbours_changed()
        self.form_message.configure(text=message)

    def add_several(self) -> None:
        rows = BulkAddDialog(self).show()
        if not rows:
            return
        added = skipped = 0
        seen = {n.farm_name.lower() for n in self.app.db.list_neighbours()}
        for name, rank in rows:
            if not name or name.lower() in seen:
                skipped += 1
                continue
            try:
                self.app.db.add_neighbour(name, rank)
            except ValidationError:
                skipped += 1
                continue
            seen.add(name.lower())
            added += 1
        self.app.neighbours_changed()
        note = f"Added {added} neighbour{'s' if added != 1 else ''}."
        if skipped:
            note += f" Skipped {skipped} (blank or already on the roster)."
        messagebox.showinfo("Neighbours added", note, parent=self)

    def toggle_archive(self) -> None:
        n = self.ds.neighbours.get(self.current_id)
        if n is None:
            return
        if n.archived:
            self.app.db.restore_neighbour(n.id)
        else:
            if not messagebox.askyesno(
                    "Archive neighbour", f"Archive {n.farm_name}?\n\nThey will disappear from new weekly updates, "
                    "but all their past results stay in the history, rankings and exports. "
                    "You can restore them at any time.", parent=self):
                return
            self.app.db.archive_neighbour(n.id)
        self.app.neighbours_changed()

    def delete(self) -> None:
        n = self.ds.neighbours.get(self.current_id)
        if n is None:
            return
        count, first, last = self.app.db.entry_count(n.id)
        span = f" (from {fmt_date(first)} to {fmt_date(last)})" if count else ""
        records = f"{count} weekly {'entry' if count == 1 else 'entries'}{span}"
        if not messagebox.askyesno(
                "Delete permanently",
                f"Permanently delete {n.farm_name}?\n\nThis will remove the neighbour and {records}. "
                "This cannot be undone.\n\nTip: choose Archive instead to keep their past results.",
                icon="warning", default="no", parent=self):
            return
        removed = self.app.db.delete_neighbour(n.id)
        self.current_id = None
        self.app.neighbours_changed()
        messagebox.showinfo("Deleted", f"Deleted {n.farm_name} and {removed} weekly "
                                       f"{'entry' if removed == 1 else 'entries'}.", parent=self)
