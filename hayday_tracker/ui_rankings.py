"""The Rankings tab: sortable weekly table, score breakdown and the active scoring settings."""
from __future__ import annotations

from tkinter import messagebox, ttk

from .db import ValidationError
from .models import MODE_CUMULATIVE
from .scoring import (COUNTERS, DERBY, DONATIONS, LABELS, LEVELS, NURTURE, OVERRIDE, RESET, SHORT_LABELS, WeekResult,
                      week_results)
from .ui_common import C, FONT, ScrollFrame, WeekPicker, make_card
from .ui_dialogs import ActualAmountDialog
from .util import fmt_date, fmt_int, fmt_num, fmt_period, fmt_score

# column id -> (heading, width, anchor, sort-key function, first-click direction is descending?)
COLUMNS = {
    "pos": ("Position", 64, "center", lambda r: r.position, False),
    "name": ("Neighbour", 130, "w", lambda r: r.neighbour.farm_name.lower(), False),
    "levels": ("Levels gained", 96, "e", lambda r: r.metrics[LEVELS].value, True),
    "nurture": ("Nurture points", 104, "e", lambda r: r.metrics[NURTURE].value, True),
    "donations": ("Donations", 84, "e", lambda r: r.metrics[DONATIONS].value, True),
    "derby": ("Derby points", 94, "e", lambda r: r.metrics[DERBY].value, True),
    "score": ("Overall score", 98, "e", lambda r: r.score, True),
    "change": ("Position change", 112, "center", lambda r: r.position_change, True),
    "notes": ("Data notes", 110, "w", lambda r: r.flags_text.lower(), False),
}


def change_text(r: WeekResult) -> str:
    if r.position is None:
        return "—"
    if r.previous_position is None:
        return "New"
    change = r.position_change
    if change == 0:
        return "– same"
    return f"▲ {change}" if change > 0 else f"▼ {-change}"


class RankingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(20, 14, 20, 12))
        self.app = app
        self.results: list[WeekResult] = []
        self.sort_col, self.sort_desc = "pos", False
        self._build()

    def _build(self) -> None:
        scroller = ScrollFrame(self, background=C["bg"], inner_style="TFrame")
        scroller.pack(fill="both", expand=True)
        self.scroller = scroller
        page = scroller.inner
        top = ttk.Frame(page)
        top.pack(fill="x")
        left = ttk.Frame(top)
        left.pack(side="left")
        ttk.Label(left, text="Rankings", style="Title.TLabel").pack(anchor="w")
        self.period = ttk.Label(left, text="", style="Heading.TLabel")
        self.period.pack(anchor="w", pady=(2, 0))
        self.summary = ttk.Label(left, text="", style="Muted.TLabel")
        self.summary.pack(anchor="w")
        right = ttk.Frame(top)
        right.pack(side="right", anchor="n", pady=6)
        ttk.Label(right, text="Reporting Monday (✓ = has data)", style="Small.TLabel").pack(anchor="e")
        row = ttk.Frame(right)
        row.pack(anchor="e", pady=(2, 0))
        self.picker = WeekPicker(row, self.app)
        self.picker.pack(side="left")
        ttk.Button(row, text="Export this week (CSV)", command=self.app.export_rankings).pack(side="left", padx=(12, 0))

        box = ttk.Frame(page)
        box.pack(fill="both", expand=True, pady=(8, 6))
        self.tree = ttk.Treeview(box, columns=list(COLUMNS), show="headings", height=8, selectmode="browse")
        for col, (text, width, anchor, _, _) in COLUMNS.items():
            self.tree.heading(col, text=text, anchor=anchor, command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=width, anchor=anchor, stretch=col == "notes")
        scroll = ttk.Scrollbar(box, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.tag_configure("missing", foreground=C["muted"])
        self.tree.tag_configure("odd", background="#FAF5E8")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_breakdown())
        self.tree.bind("<Double-1>", lambda e: self.set_actual())
        ttk.Label(page, text=("Click any heading to sort. * after a number means you supplied the actual amount after "
                              "a counter reset. Select a row to see exactly how its score was calculated."),
                  style="Small.TLabel").pack(anchor="w")

        lower = ttk.Frame(page)
        lower.pack(fill="x", pady=(8, 0))
        o1, breakdown = make_card(lower, padding=12)
        o1.pack(fill="x")
        self.breakdown_title = ttk.Label(breakdown, text="How the score was calculated", style="CardHeading.TLabel")
        self.breakdown_title.pack(anchor="w")
        cols = ("metric", "raw", "result", "target", "pct", "weight", "points")
        self.bd = ttk.Treeview(breakdown, columns=cols, show="headings", height=4, selectmode="none")
        for col, text, width, anchor in (("metric", "Metric", 110, "w"), ("raw", "Raw figures", 200, "w"),
                                         ("result", "Weekly result", 130, "e"), ("target", "Target", 70, "e"),
                                         ("pct", "% of target", 100, "e"), ("weight", "Weight", 70, "e"),
                                         ("points", "Points", 120, "e")):
            self.bd.heading(col, text=text, anchor=anchor)
            self.bd.column(col, width=width, anchor=anchor, stretch=col == "raw")
        self.bd.pack(fill="x", pady=(6, 4))
        self.bd.tag_configure("total", font=(FONT, 10, "bold"))
        self.bd_note = ttk.Label(breakdown, text="Select a neighbour above.", style="CardMuted.TLabel",
                                 wraplength=760, justify="left")
        self.bd_note.pack(anchor="w")
        self.actual_button = ttk.Button(breakdown, text="Enter actual amount earned…", command=self.set_actual)

        o2, settings = make_card(lower, padding=12)
        o2.pack(fill="x", pady=(8, 0))
        head = ttk.Frame(settings, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Active scoring settings", style="CardHeading.TLabel").pack(side="left")
        ttk.Button(head, text="Edit settings…", command=self.app.edit_settings).pack(side="right")
        grid = ttk.Frame(settings, style="Card.TFrame")
        grid.pack(fill="x", pady=(6, 4))
        self.setting_labels = {}
        for i, key in enumerate((NURTURE, DONATIONS, DERBY, LEVELS)):
            grid.columnconfigure(i, weight=1, uniform="settings")
            label = ttk.Label(grid, text="", style="Card.TLabel", justify="left", wraplength=200)
            label.grid(row=0, column=i, sticky="nw", padx=(0, 12))
            self.setting_labels[key] = label
        self.formula = ttk.Label(settings, text="Score = sum of  min(result ÷ target, 100%) × weight  for the three metrics, "
                                                "out of 100.", style="CardMuted.TLabel", font=(FONT, 9))
        self.formula.pack(anchor="w")

    # ------------------------------------------------------------------- data
    def refresh(self) -> None:
        week = self.app.week
        ds = self.app.db.load_dataset()
        self.results = week_results(ds, week, self.app.settings)
        self.picker.refresh()
        self.period.configure(text=f"Reporting period: {fmt_period(week)}")
        scored = sum(1 for r in self.results if r.score is not None)
        self.summary.configure(
            text=(f"Reporting date {fmt_date(week)}.  {scored} of {len(self.results)} neighbours have a score"
                  + (f"; the rest show Insufficient data." if scored < len(self.results) else ".")
                  if self.results else f"Reporting date {fmt_date(week)}.  No neighbours to rank yet."))
        self._show_settings()
        self._fill()

    def _show_settings(self) -> None:
        s = self.app.settings

        for key, name in ((NURTURE, "Nurture"), (DONATIONS, "Donations"), (DERBY, "Derby"), (LEVELS, "Levels gained")):
            mode = getattr(s, f"{key}_mode", None)
            if mode is None:
                how = "change since last Monday"
            else:
                how = f"{mode} counter: " + ("change since last Monday" if mode == MODE_CUMULATIVE
                                             else "used directly")
            self.setting_labels[key].configure(
                text=f"{name}\n{how}\nweight {fmt_num(getattr(s, f'weight_{key}'))}%, "
                     f"target {fmt_num(getattr(s, f'target_{key}'))} per week")

    def sort_by(self, col: str) -> None:
        if col == self.sort_col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = col, COLUMNS[col][4]
        self._fill()

    def _fill(self) -> None:
        keep = self.selected_id()
        key = COLUMNS[self.sort_col][3]
        present = [r for r in self.results if key(r) is not None]
        absent = [r for r in self.results if key(r) is None]     # missing values always sink to the bottom
        present.sort(key=lambda r: r.neighbour.farm_name.lower())     # A to Z within equal values
        present.sort(key=key, reverse=self.sort_desc)                  # stable, so that order is kept
        absent.sort(key=lambda r: r.neighbour.farm_name.lower())
        ordered = present + absent

        for col, (text, *_rest) in COLUMNS.items():
            arrow = (" ▼" if self.sort_desc else " ▲") if col == self.sort_col else ""
            self.tree.heading(col, text=text + arrow)
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(ordered):
            tags = []
            if r.score is None:
                tags.append("missing")
            elif i % 2:
                tags.append("odd")
            self.tree.insert("", "end", iid=str(r.neighbour.id), tags=tags, values=(
                fmt_int(r.position), r.neighbour.label, r.metrics[LEVELS].text, r.metrics[NURTURE].text,
                r.metrics[DONATIONS].text, r.metrics[DERBY].text, fmt_score(r.score), change_text(r), r.flags_text))
        if keep is not None and self.tree.exists(str(keep)):
            self.tree.selection_set(str(keep))
        else:
            self.show_breakdown()

    def selected_id(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def selected_result(self) -> WeekResult | None:
        nid = self.selected_id()
        return next((r for r in self.results if r.neighbour.id == nid), None)

    # -------------------------------------------------------------- breakdown
    def show_breakdown(self) -> None:
        self.bd.delete(*self.bd.get_children())
        self.actual_button.pack_forget()
        r = self.selected_result()
        if r is None:
            self.breakdown_title.configure(text="How the score was calculated")
            self.bd_note.configure(text="Select a neighbour above.")
            return
        self.breakdown_title.configure(text=f"How {r.neighbour.farm_name}'s score was calculated")
        s = self.app.settings
        for key in (NURTURE, DONATIONS, DERBY, LEVELS):
            m, p = r.metrics[key], r.parts[key]
            if key == LEVELS:
                raw = (f"Level {m.current}, last week {m.previous}" if m.previous is not None
                       else (f"Level {m.current}, no baseline" if m.current is not None else "Not entered"))
            elif getattr(s, f"{key}_mode") == MODE_CUMULATIVE:
                raw = (f"Total {m.current:,}, last week {m.previous:,}" if m.previous is not None
                       else (f"Total {m.current:,}, no baseline" if m.current is not None else "Not entered"))
            else:
                raw = f"This week {m.current:,}" if m.current is not None else "Not entered"
            self.bd.insert("", "end", values=(
                LABELS[key], raw, m.text, fmt_num(p.target),
                "—" if p.fraction is None else f"{p.fraction * 100:.0f}%", f"{fmt_num(p.weight)}%",
                "—" if p.points is None else f"{p.points:.2f}"))
        self.bd.insert("", "end", tags=("total",), values=(
            "Overall score", "", "", "", "", f"{fmt_num(sum(p.weight for p in r.parts.values()))}%", fmt_score(r.score)))

        notes = []
        if r.score is None:
            gaps = ", ".join(SHORT_LABELS[k].lower() for k in r.missing_required)
            notes.append(f"Insufficient data: {gaps} {'is' if len(r.missing_required) == 1 else 'are'} missing, "
                         "so no overall score or leaderboard position is given.")
        else:
            tied = sum(1 for o in self.results if o is not r and o.score == r.score)
            before = f"position {r.previous_position}" if r.previous_position else "not ranked"
            notes.append(f"Leaderboard position {r.position}"
                         + (f" (tied with {tied} other{'s' if tied != 1 else ''})" if tied else "")
                         + f". Previous week: {before}.")
        for key in (NURTURE, DONATIONS, DERBY, LEVELS):
            if r.metrics[key].note:
                notes.append(f"{SHORT_LABELS[key]}: {r.metrics[key].note}.")
        self.bd_note.configure(text="\n".join(notes))
        if any(r.metrics[k].status in (RESET, OVERRIDE) for k in COUNTERS):
            self.actual_button.pack(anchor="w", pady=(8, 0))

    def set_actual(self) -> None:
        """Supply the actual amount earned for a counter that dropped (reset)."""
        r = self.selected_result()
        if r is None or r.entry is None:
            return
        for key in COUNTERS:
            m = r.metrics[key]
            if m.status not in (RESET, OVERRIDE):
                continue
            existing = getattr(r.entry, f"{key}_actual")
            result = ActualAmountDialog(self, r.neighbour.farm_name, key, m.previous, m.current, existing).show()
            if result is None:
                return
            try:
                self.app.db.set_actual(r.neighbour.id, r.week, key, result[0])
            except ValidationError as exc:
                messagebox.showwarning("Could not save", str(exc), parent=self)
                return
            self.app.data_changed(source=self)
