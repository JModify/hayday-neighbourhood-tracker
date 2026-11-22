"""The Monday Update tab: one scrollable, keyboard-friendly entry grid for the whole roster."""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

from .models import MODE_CUMULATIVE, Entry, EntryInput, Neighbour
from .ui_common import C, FONT, ScrollFrame, WeekPicker
from .ui_dialogs import ActualAmountDialog
from .util import (MAX_COUNT, MAX_LEVEL, cutoff_for, fmt_cutoff, fmt_date, fmt_int, fmt_period, fmt_remaining,
                   is_week_locked, now_brisbane, parse_count)

# (key, pixel width). The header and the body use the same widths so they line up.
COLUMNS = [("name", 140), ("rank", 72), ("lvl_last", 46), ("lvl", 62), ("nur_last", 66), ("nur", 82),
           ("don_last", 62), ("don", 78), ("der_last", 62), ("der", 78), ("status", 150)]
HEAD_BG = "#E9E1CD"
HINT_OPEN = ("Tab moves across the fields, Enter or ↓ moves down a row, ↑ moves up. "
             "Leave a box empty if you don't have the number yet; empty is not the same as 0. "
             "A row only counts as entered when all four numbers are filled in. "
             "You can save part-way and come back to it until the week closes.")
RANK_ORDER = {"leader": 0, "co-leader": 1, "coleader": 1, "elder": 2, "member": 3}


def rank_sort_key(n: Neighbour):
    """Numbers first (1, 2, 3...), then Leader / Elder / Member, then anything else."""
    rank = n.game_rank.strip().lower()
    name = n.farm_name.lower()
    if rank.isdigit():
        return (0, int(rank), name)
    if rank in RANK_ORDER:
        return (1, RANK_ORDER[rank], name)
    return (3 if not rank else 2, rank, name)


def _snap(text: str, minimum: int, maximum: int):
    value, error = parse_count(text, minimum, maximum)
    return ("raw", text.strip()) if error else value


class Row:
    """One neighbour's row in the grid."""

    FIELDS = ("lvl", "nur", "don", "der")
    # field key -> (Entry attribute, counter key used by scoring/settings, smallest allowed, largest allowed, label)
    SPEC = {"lvl": ("farm_level", None, 1, MAX_LEVEL, "Farm level"),
            "nur": ("nurture", "nurture", 0, MAX_COUNT, "Nurture score"),
            "don": ("donations", "donations", 0, MAX_COUNT, "Total donations"),
            "der": ("derby", "derby", 0, MAX_COUNT, "Derby score")}
    COUNTER_FIELDS = {"nurture": "nur", "donations": "don", "derby": "der"}
    COUNTER_NAMES = {"nurture": "Nurture", "donations": "Donations", "derby": "Derby"}

    def __init__(self, tab: "MondayTab", index: int, n: Neighbour, entry: Entry | None, prev: Entry | None):
        self.tab, self.index, self.n, self.prev = tab, index, n, prev
        self.has_saved = entry is not None
        inner = tab.body.inner
        r = index
        pad = dict(padx=4, pady=3)

        name = n.farm_name + ("  (archived)" if n.archived else "")
        ttk.Label(inner, text=name, style="Card.TLabel", font=(FONT, 10, "bold"),
                  foreground=C["muted"] if n.archived else C["text"]).grid(row=r, column=0, sticky="w", **pad)
        ttk.Label(inner, text=n.game_rank or "—", style="CardMuted.TLabel").grid(row=r, column=1, sticky="w", **pad)

        self.vars = {k: tk.StringVar() for k in self.FIELDS}
        self.entries: dict[str, ttk.Entry] = {}
        for i, key in enumerate(self.FIELDS):
            col = 2 + 2 * i
            last = getattr(prev, self.SPEC[key][0]) if prev else None
            ttk.Label(inner, text=fmt_int(last), style="CardMuted.TLabel", anchor="e"
                      ).grid(row=r, column=col, sticky="ew", padx=(4, 8), pady=3)
            box = ttk.Entry(inner, textvariable=self.vars[key], width=9, justify="right")
            box.grid(row=r, column=col + 1, sticky="ew", **pad)
            self.entries[key] = box
            box.bind("<FocusIn>", lambda e, w=box: self._focus_in(w))
            box.bind("<Return>", lambda e, k=key: self._move(k, +1))
            box.bind("<Down>", lambda e, k=key: self._move(k, +1))
            box.bind("<Up>", lambda e, k=key: self._move(k, -1))

        self.status = ttk.Label(inner, text="", style="Card.TLabel", wraplength=140, justify="left")
        self.status.grid(row=r, column=2 + 2 * len(self.FIELDS), sticky="w", padx=(8, 4), pady=3)
        self.status.bind("<Button-1>", lambda e: self.fix_drops())

        # Starting values: a saved entry wins; otherwise prefill only the farm level from last week.
        self.prefill_level: int | None = None
        if entry is not None:
            texts = {k: getattr(entry, self.SPEC[k][0]) for k in self.FIELDS}
            self.actual = {"nurture": entry.nurture_actual, "donations": entry.donations_actual,
                           "derby": entry.derby_actual}
        else:
            self.prefill_level = prev.farm_level if prev else None
            texts = {k: None for k in self.FIELDS}
            texts["lvl"] = self.prefill_level
            self.actual = {"nurture": None, "donations": None, "derby": None}
        for key, value in texts.items():
            self.vars[key].set("" if value is None else str(value))
        self.initial = self._snapshot()
        for var in self.vars.values():
            var.trace_add("write", lambda *_: self._changed())
        if tab.locked:
            for box in self.entries.values():
                box.state(["disabled"])
        self.refresh()

    # ----------------------------------------------------------------- state
    def _parsed(self):
        """``{field: (value, error)}`` for every box."""
        return {k: parse_count(self.vars[k].get(), self.SPEC[k][2], self.SPEC[k][3]) for k in self.FIELDS}

    def drops(self) -> list[str]:
        """Cumulative counters whose new total is below last Monday's."""
        if self.prev is None:
            return []
        parsed = self._parsed()
        settings = self.tab.app.settings
        out = []
        for counter, field in self.COUNTER_FIELDS.items():
            value, before = parsed[field][0], getattr(self.prev, counter)
            if getattr(settings, f"{counter}_mode") == MODE_CUMULATIVE and value is not None \
                    and before is not None and value < before:
                out.append(counter)
        return out

    def _effective_actuals(self):
        drops = self.drops()
        return tuple(self.actual[k] if k in drops else None for k in self.COUNTER_FIELDS)

    def _snapshot(self):
        return tuple(_snap(self.vars[k].get(), self.SPEC[k][2], self.SPEC[k][3])
                     for k in self.FIELDS) + self._effective_actuals()

    def values(self):
        parsed = self._parsed()
        return tuple(parsed[k][0] for k in self.FIELDS)

    def is_blank(self) -> bool:
        return all(v is None for v in self.values())

    def dirty(self) -> bool:
        if self.is_blank() and not self.has_saved:
            return False
        return self._snapshot() != self.initial

    def has_errors(self) -> bool:
        return any(err for _, err in self._parsed().values())

    def started(self) -> bool:
        lvl, nur, don, der = self.values()
        return (nur is not None or don is not None or der is not None
                or (lvl is not None and lvl != self.prefill_level))

    def complete(self) -> bool:
        """All four values are in: farm level, Nurture, donations and Derby. None may be left blank."""
        return not self.has_errors() and None not in self.values()

    def to_input(self) -> EntryInput:
        lvl, nur, don, der = self.values()
        actual_n, actual_d, actual_der = self._effective_actuals()
        return EntryInput(self.n.id, lvl, nur, don, actual_n, actual_d, der, actual_der)

    def draft(self) -> dict:
        data = {k: self.vars[k].get() for k in self.FIELDS}
        data["actual"] = dict(self.actual)
        return data

    def apply_draft(self, draft: dict) -> None:
        for key in self.FIELDS:
            self.vars[key].set(draft[key])
        self.actual = dict(draft["actual"])
        self.refresh()

    # ---------------------------------------------------------------- display
    def _changed(self) -> None:
        self.refresh()
        self.tab.update_progress()

    def refresh(self) -> None:
        parsed = self._parsed()
        drops = self.drops()
        lvl = parsed["lvl"][0]
        level_low = bool(self.prev and lvl is not None and self.prev.farm_level is not None
                         and lvl < self.prev.farm_level)
        errors = []
        for key, entry in self.entries.items():
            error = parsed[key][1]
            counter = self.SPEC[key][1]
            drop = counter in drops
            if error:
                entry.configure(style="Invalid.TEntry")
                errors.append(f"{self.SPEC[key][4]} {error}")
            elif drop or (key == "lvl" and level_low):
                entry.configure(style="Warn.TEntry")
            else:
                entry.configure(style="TEntry")

        notes, style = [], "Card.TLabel"
        if errors:
            text, style = "✗ " + errors[0] + (f"  (+{len(errors) - 1} more)" if len(errors) > 1 else ""), "CardBad.TLabel"
        else:
            if self.complete():
                text, style = "✓ Entered", "CardGood.TLabel"
            elif self.started():
                text, style = "Partly entered", "CardWarn.TLabel"
            else:
                text, style = "Not entered", "CardMuted.TLabel"
            for key in self.COUNTER_FIELDS:
                if key in drops:
                    got = self.actual[key]
                    if self.tab.locked:
                        notes.append(f"⚠ {self.COUNTER_NAMES[key]} total dropped"
                                     + (f". Actual earned: {got:,}" if got is not None else ""))
                    else:
                        notes.append(f"⚠ {self.COUNTER_NAMES[key]} total dropped. " +
                                     (f"Actual earned: {got:,} (click to change)" if got is not None
                                      else "Click to enter the actual amount earned"))
            if level_low:
                notes.append("⚠ Farm level is lower than last week")
            if notes:
                text += "\n" + "\n".join(notes)
                if style != "CardBad.TLabel":
                    style = "CardWarn.TLabel" if style != "CardGood.TLabel" else "CardGood.TLabel"
        self.status.configure(text=text, style=style, cursor="hand2" if drops and not self.tab.locked else "")

    def fix_drops(self) -> None:
        if self.tab.locked:
            return
        for key in self.drops():
            if not self.ask_actual(key):
                break

    def ask_actual(self, key: str) -> bool:
        current = self._parsed()[self.COUNTER_FIELDS[key]][0]
        previous = getattr(self.prev, key)
        result = ActualAmountDialog(self.tab, self.n.farm_name, key, previous, current, self.actual[key]).show()
        if result is None:
            return False
        self.actual[key] = result[0]
        self.refresh()
        self.tab.update_progress()
        return True

    # ------------------------------------------------------------- navigation
    def _focus_in(self, widget: ttk.Entry) -> None:
        widget.after_idle(lambda: widget.select_range(0, "end"))
        self.tab.body.see(widget)

    def _move(self, key: str, delta: int):
        target = self.index + delta
        if 0 <= target < len(self.tab.rows):
            w = self.tab.rows[target].entries[key]
            w.focus_set()
        return "break"


class MondayTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(20, 14, 20, 12))
        self.app = app
        self.rows: list[Row] = []
        self.week: date | None = None
        self.stale = False
        self._status_after = None
        self._built_locked = False
        self._build()

    @property
    def locked(self) -> bool:
        """True once this week's 6 PM Monday (Brisbane) cutoff has passed: the grid is read-only."""
        return self.week is not None and is_week_locked(self.week)

    def update_lock_banner(self) -> None:
        """Say whether the week is open, and when it closes. Called on load and every few seconds."""
        if self.week is None:
            return
        now = now_brisbane()
        cutoff = cutoff_for(self.week)
        if now >= cutoff:
            self.lock_label.configure(
                text=f"🔒 Closed at {fmt_cutoff(self.week)} (Brisbane time), when Hay Day resets. "
                     "This week is read-only.", style="Bad.TLabel")
            self.hint.configure(text="This week has closed, so it can no longer be changed. "
                                     "Open the current week to enter new numbers.")
        else:
            left = cutoff - now
            soon = left.total_seconds() < 2 * 3600
            self.lock_label.configure(
                text=f"Open for entry until {fmt_cutoff(self.week)} Brisbane time ({fmt_remaining(left)} left). "
                     "Until then you can keep saving changes.", style="Warn.TLabel" if soon else "Good.TLabel")
            self.hint.configure(text=HINT_OPEN)
        state = "disabled" if self.locked else "normal"
        self.save_button.configure(state=state)
        self.discard_button.configure(state=state)
        if self.locked != self._built_locked and self.rows:
            self.reload_keeping_drafts()      # grid was built for the other state: rebuild it

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x")
        left = ttk.Frame(top)
        left.pack(side="left")
        ttk.Label(left, text="Monday Update", style="Title.TLabel").pack(anchor="w")
        self.period = ttk.Label(left, text="", style="Heading.TLabel")
        self.period.pack(anchor="w", pady=(2, 0))
        self.reporting = ttk.Label(left, text="", style="Muted.TLabel")
        self.reporting.pack(anchor="w")
        self.lock_label = ttk.Label(left, text="", style="Good.TLabel", font=(FONT, 10, "bold"))
        self.lock_label.pack(anchor="w", pady=(2, 0))
        picker_box = ttk.Frame(top)
        picker_box.pack(side="right", anchor="n", pady=6)
        ttk.Label(picker_box, text="Reporting Monday (✓ = has data)", style="Small.TLabel").pack(anchor="e")
        self.picker = WeekPicker(picker_box, self.app)
        self.picker.pack(anchor="e", pady=(2, 0))

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(12, 6))
        self.progress_label = ttk.Label(bar, text="", font=(FONT, 11, "bold"))
        self.progress_label.pack(side="left")
        self.progress = ttk.Progressbar(bar, length=220, mode="determinate")
        self.progress.pack(side="left", padx=14)
        self.save_button = ttk.Button(bar, text="Save update", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="right")
        self.discard_button = ttk.Button(bar, text="Discard changes", command=self.discard)
        self.discard_button.pack(side="right", padx=8)
        self.state_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self.state_label.pack(side="right", padx=12)

        self.hint = ttk.Label(self, text=HINT_OPEN, style="Small.TLabel", wraplength=900, justify="left")
        self.hint.pack(anchor="w", pady=(0, 8))
        self.bind("<Configure>", lambda e: self.hint.configure(wraplength=max(300, e.width - 60)))

        self.frame_header = tk.Frame(self, bg=HEAD_BG)
        self.frame_header.pack(fill="x")
        self.body = ScrollFrame(self)
        self.body.pack(fill="both", expand=True)
        self.body.canvas.bind("<Configure>", lambda e: self._fit_status(e.width), add="+")

    def _fit_status(self, canvas_width: int) -> None:
        """Let the Status text use whatever width is left beside the entry columns."""
        spare = canvas_width - sum(w for _, w in COLUMNS[:-1]) - 24
        wrap = max(COLUMNS[-1][1] - 16, spare - 16)
        for row in self.rows:
            row.status.configure(wraplength=wrap)

    def _build_header(self) -> None:
        for child in self.frame_header.winfo_children():
            child.destroy()
        s = self.app.settings
        kind = {k: "total" if getattr(s, f"{k}_mode") == MODE_CUMULATIVE else "weekly"
                for k in ("nurture", "donations", "derby")}
        head = self.frame_header
        for i, (_, width) in enumerate(COLUMNS):
            head.grid_columnconfigure(i, minsize=width, weight=1 if i == len(COLUMNS) - 1 else 0)

        def label(text, row, col, span=1, rowspan=1, anchor="w", bold=True, muted=False):
            tk.Label(head, text=text, bg=HEAD_BG, fg=C["muted"] if muted else C["text"], anchor=anchor,
                     font=(FONT, 10 if bold else 9, "bold" if bold else "normal")
                     ).grid(row=row, column=col, columnspan=span, rowspan=rowspan, sticky="nsew", padx=4,
                            pady=(6, 0) if row == 0 else (0, 6))

        label("Neighbour", 0, 0, rowspan=2)
        label("In-game rank", 0, 1, rowspan=2)
        label("Farm level", 0, 2, span=2, anchor="center")
        label(f"Nurture ({kind['nurture']})", 0, 4, span=2, anchor="center")
        label(f"Donations ({kind['donations']})", 0, 6, span=2, anchor="center")
        label(f"Derby ({kind['derby']})", 0, 8, span=2, anchor="center")
        label("Status", 0, 10, rowspan=2)
        for col in (2, 4, 6, 8):
            label("Last week", 1, col, anchor="e", bold=False, muted=True)
            label("This week", 1, col + 1, anchor="e", bold=False, muted=True)
        # Match the width of the body's scrollbar so columns line up exactly.
        head.grid_columnconfigure(len(COLUMNS), minsize=self.body.scrollbar_width())

    # ------------------------------------------------------------------- data
    def load_week(self, week: date, drafts: dict[int, dict] | None = None) -> None:
        """(Re)build the grid for ``week``. ``drafts`` re-applies unsaved typing by neighbour."""
        self.week = week
        self.stale = False
        self._built_locked = self.locked
        ds = self.app.db.load_dataset()
        entries = ds.entries.get(week, {})
        previous = ds.entries.get(week - timedelta(days=7), {})
        people = [n for n in ds.neighbours.values() if not n.archived or n.id in entries]
        people.sort(key=rank_sort_key)

        for child in self.body.inner.winfo_children():
            child.destroy()
        self.rows = []
        self._build_header()
        for i, col in enumerate(COLUMNS):
            self.body.inner.grid_columnconfigure(i, minsize=col[1], weight=1 if i == len(COLUMNS) - 1 else 0)

        self.period.configure(text=f"Reporting period: {fmt_period(week)}")
        self.reporting.configure(text=f"Reporting date {fmt_date(week)}. Covers the week that ended on the Sunday before.")
        self.picker.refresh()
        self.update_lock_banner()

        if not people:
            self._empty_state()
        for i, n in enumerate(people):
            self.rows.append(Row(self, i, n, entries.get(n.id), previous.get(n.id)))
        for row in self.rows:
            if drafts and row.n.id in drafts:
                row.apply_draft(drafts[row.n.id])
        self.update_progress()
        self.body.refit()
        self.body.canvas.yview_moveto(0)

    def focus_first_empty(self) -> None:
        """Put the cursor on the first Nurture box still waiting for a number."""
        if not self.rows or self.locked:
            return
        target = next((r for r in self.rows if not r.vars["nur"].get().strip()), self.rows[0])
        target.entries["nur"].focus_set()

    def _empty_state(self) -> None:
        box = ttk.Frame(self.body.inner, style="Card.TFrame", padding=40)
        box.grid(row=0, column=0, columnspan=len(COLUMNS), sticky="ew")
        ttk.Label(box, text="No neighbours yet", style="CardHeading.TLabel").pack()
        ttk.Label(box, text="Add your neighbours first, then come back here to enter this Monday's numbers.",
                  style="CardMuted.TLabel").pack(pady=(4, 12))
        ttk.Button(box, text="Go to Neighbours", style="Primary.TButton",
                   command=lambda: self.app.show_tab("neighbours")).pack()

    def capture_drafts(self) -> dict[int, dict]:
        return {r.n.id: r.draft() for r in self.rows if r.dirty()}

    def reload_keeping_drafts(self) -> None:
        if self.week is not None:
            self.load_week(self.week, self.capture_drafts())

    def has_unsaved(self) -> bool:
        return any(r.dirty() for r in self.rows)

    def update_progress(self) -> None:
        total = len(self.rows)
        done = sum(1 for r in self.rows if r.complete())
        partial = sum(1 for r in self.rows if not r.complete() and not r.has_errors() and r.started())
        invalid = sum(1 for r in self.rows if r.has_errors())
        text = f"{done} of {total} neighbours entered"
        if partial:
            text += f"  ·  {partial} partly entered"
        if invalid:
            text += f"  ·  {invalid} need fixing"
        self.progress_label.configure(text=text if total else "No neighbours to enter")
        self.progress.configure(maximum=max(total, 1), value=done)
        unsaved = sum(1 for r in self.rows if r.dirty())
        if unsaved:
            self.state_label.configure(text=f"● {unsaved} unsaved {'row' if unsaved == 1 else 'rows'}",
                                       foreground=C["warn"])
        elif self._status_after is None:
            self.state_label.configure(text="", foreground=C["muted"])

    # ---------------------------------------------------------------- actions
    def _flash(self, text: str) -> None:
        self.state_label.configure(text=text, foreground=C["ok"])
        if self._status_after:
            self.after_cancel(self._status_after)

        def clear():
            self._status_after = None
            self.update_progress()
        self._status_after = self.after(6000, clear)

    def save(self) -> bool:
        if self.locked:
            messagebox.showwarning("Week closed", f"Entry for {fmt_cutoff(self.week)} Brisbane time has closed, "
                                   "so this week can no longer be changed.", parent=self)
            return False
        bad = [r for r in self.rows if r.has_errors()]
        if bad:
            messagebox.showwarning(
                "Check the highlighted fields",
                f"{len(bad)} {'row has' if len(bad) == 1 else 'rows have'} a value that can't be saved "
                "(highlighted in red). Nothing was saved yet. Fix them and save again.", parent=self)
            first = next(k for k, e in bad[0].entries.items() if str(e.cget("style")) == "Invalid.TEntry")
            bad[0].entries[first].focus_set()
            return False
        changed = [r for r in self.rows if r.dirty()]
        if not changed:
            self._flash("Nothing new to save")
            return True
        try:
            saved, cleared = self.app.db.save_week(self.week, [r.to_input() for r in changed])
        except Exception as exc:  # a failed save rolls everything back
            messagebox.showerror("Could not save", f"Nothing was saved.\n\n{exc}", parent=self)
            return False
        self.app.data_changed(source=self)
        self.load_week(self.week)
        parts = [f"{saved} saved"] + ([f"{cleared} cleared"] if cleared else [])
        self._flash("✓ " + ", ".join(parts) + f" at {datetime.now():%I:%M %p}".replace(" 0", " "))
        return True

    def discard(self) -> None:
        if self.locked:
            return
        if self.has_unsaved() and not messagebox.askyesno(
                "Discard changes", "Throw away everything you've typed since the last save?",
                icon="warning", default="no", parent=self):
            return
        self.load_week(self.week)

    def confirm_leave(self) -> bool:
        """Ask what to do with unsaved typing. Returns False if the user cancels."""
        if not self.has_unsaved():
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", f"You have unsaved changes for {fmt_date(self.week)}.\n\n"
            "Save them before continuing?", icon="warning", parent=self)
        if answer is None:
            return False
        if answer:
            return self.save()
        return True
