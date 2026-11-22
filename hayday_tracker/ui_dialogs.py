"""Dialog windows: scoring settings, counter-reset amounts and bulk roster entry."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .models import MODE_CUMULATIVE, MODE_WEEKLY, Settings
from .scoring import COUNTERS, DERBY, DONATIONS, LEVELS, NURTURE, SHORT_LABELS
from .ui_common import C, Dialog
from .util import MAX_COUNT, fmt_num, parse_count

MODE_LABELS = {
    MODE_WEEKLY: "Weekly: the number I enter is what was earned that week",
    MODE_CUMULATIVE: "Cumulative: the number I enter is a running total (use the change since last Monday)",
}


class SettingsDialog(Dialog):
    """Counter types, score weights and weekly targets."""

    def __init__(self, parent, settings: Settings):
        super().__init__(parent, "Scoring settings")
        self.initial = settings
        b = self.body
        ttk.Label(b, text="Scoring settings", style="Heading.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(b, text="Changes recalculate every week, including past ones.", style="Muted.TLabel"
                  ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))

        self.mode_vars = {}
        reverse = {v: k for k, v in MODE_LABELS.items()}
        self._reverse_modes = reverse
        for i, key in enumerate(COUNTERS):
            ttk.Label(b, text=f"{SHORT_LABELS[key]} counter").grid(row=2 + i, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=MODE_LABELS[getattr(settings, f"{key}_mode")])
            ttk.Combobox(b, textvariable=var, values=list(MODE_LABELS.values()), state="readonly",
                         width=72).grid(row=2 + i, column=1, columnspan=3, sticky="w", padx=(10, 0), pady=4)
            self.mode_vars[key] = var
        ttk.Label(b, text="Farm level is always scored on the change since the previous Monday.",
                  style="Small.TLabel").grid(row=5, column=1, columnspan=3, sticky="w", padx=(10, 0))

        ttk.Separator(b).grid(row=6, column=0, columnspan=4, sticky="ew", pady=12)
        for col, text in enumerate(("Metric", "Weight (%)", "Weekly target")):
            ttk.Label(b, text=text, font=("Segoe UI", 10, "bold")).grid(row=7, column=col, sticky="w",
                                                                    padx=(0 if col == 0 else 10, 0))
        self.weight_vars, self.target_vars = {}, {}
        unit = {NURTURE: "Nurture points", DONATIONS: "Donations", DERBY: "Derby points", LEVELS: "Levels gained"}
        for i, key in enumerate((NURTURE, DONATIONS, DERBY, LEVELS)):
            ttk.Label(b, text=unit[key]).grid(row=8 + i, column=0, sticky="w", pady=4)
            wv = tk.StringVar(value=fmt_num(getattr(settings, f"weight_{key}")))
            tv = tk.StringVar(value=fmt_num(getattr(settings, f"target_{key}")))
            ttk.Entry(b, textvariable=wv, width=10, justify="right").grid(row=8 + i, column=1, sticky="w", padx=(10, 0))
            ttk.Entry(b, textvariable=tv, width=10, justify="right").grid(row=8 + i, column=2, sticky="w", padx=(10, 0))
            wv.trace_add("write", lambda *_: self._update_total())
            self.weight_vars[key], self.target_vars[key] = wv, tv
        self.total_label = ttk.Label(b, text="")
        self.total_label.grid(row=12, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(b, text="Each metric: result ÷ target, capped at 100% of the target, × weight. "
                          "The results add up to a score out of 100. A metric with a weight of 0 is recorded but not scored "
                          "(Derby starts at 0).",
                  style="Small.TLabel", wraplength=560, justify="left"
                  ).grid(row=13, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.error = ttk.Label(b, text="", style="Bad.TLabel", wraplength=560, justify="left")
        self.error.grid(row=14, column=0, columnspan=4, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(b)
        buttons.grid(row=15, column=0, columnspan=4, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Restore defaults", command=self._defaults).pack(side="left", padx=(0, 20))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="left", padx=4)
        ttk.Button(buttons, text="Save settings", style="Primary.TButton", command=self._save).pack(side="left")
        self._update_total()

    def _defaults(self) -> None:
        d = Settings()
        for key in COUNTERS:
            self.mode_vars[key].set(MODE_LABELS[getattr(d, f"{key}_mode")])
        for key in (NURTURE, DONATIONS, DERBY, LEVELS):
            self.weight_vars[key].set(fmt_num(getattr(d, f"weight_{key}")))
            self.target_vars[key].set(fmt_num(getattr(d, f"target_{key}")))

    def _number(self, text: str) -> float | None:
        try:
            return float(text.strip().replace(",", ""))
        except ValueError:
            return None

    def _update_total(self) -> None:
        values = [self._number(v.get()) for v in self.weight_vars.values()]
        if None in values:
            self.total_label.configure(text="Weights add up to: —", style="Bad.TLabel")
            return
        total = sum(values)
        good = abs(total - 100) < 1e-6
        self.total_label.configure(text=f"Weights add up to {fmt_num(total)}%" + ("" if good else "  (must be 100%)"),
                                   style="Good.TLabel" if good else "Bad.TLabel")

    def _save(self) -> None:
        s = Settings()
        for key in COUNTERS:
            setattr(s, f"{key}_mode", self._reverse_modes[self.mode_vars[key].get()])
        for key in (NURTURE, DONATIONS, DERBY, LEVELS):
            w, t = self._number(self.weight_vars[key].get()), self._number(self.target_vars[key].get())
            if w is None or t is None:
                self.error.configure(text="Weights and targets must be numbers.")
                return
            setattr(s, f"weight_{key}", w)
            setattr(s, f"target_{key}", t)
        problems = s.problems()
        if problems:
            self.error.configure(text=" ".join(problems))
            return
        self.result = s
        self.destroy()


class ActualAmountDialog(Dialog):
    """Ask for the amount really earned after a cumulative counter dropped."""

    CLEAR = "clear"

    def __init__(self, parent, name: str, metric: str, previous: int, current: int, existing: int | None):
        super().__init__(parent, "Counter dropped")
        label = SHORT_LABELS[metric].lower()
        b = self.body
        ttk.Label(b, text=f"{name}: {label} total went down", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(b, text=(f"Last Monday's total was {previous:,} and this week's is {current:,}, so the "
                           f"counter looks like it was reset.\n\nIf you know how many {label} {name} actually "
                           f"earned that week, enter it below. Otherwise leave it empty and this week's "
                           f"{label} result stays missing (no overall score)."),
                  wraplength=460, justify="left").pack(anchor="w", pady=(8, 12))
        row = ttk.Frame(b)
        row.pack(anchor="w")
        ttk.Label(row, text=f"Actual {label} earned:").pack(side="left")
        self.var = tk.StringVar(value="" if existing is None else str(existing))
        self.entry = ttk.Entry(row, textvariable=self.var, width=12, justify="right")
        self.entry.pack(side="left", padx=8)
        self.entry.bind("<Return>", lambda e: self._ok())
        self.error = ttk.Label(b, text="", style="Bad.TLabel")
        self.error.pack(anchor="w", pady=(6, 0))
        buttons = ttk.Frame(b)
        buttons.pack(anchor="e", pady=(14, 0), fill="x")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", style="Primary.TButton", command=self._ok).pack(side="right")
        self.entry.focus_set()

    def _ok(self) -> None:
        value, error = parse_count(self.var.get(), 0, MAX_COUNT)
        if error:
            self.error.configure(text=f"Amount {error}.")
            return
        self.result = (value,)   # a one-item tuple so that "cleared" (None) differs from cancelled
        self.destroy()


class BulkAddDialog(Dialog):
    """Add several neighbours at once, one per line."""

    def __init__(self, parent):
        super().__init__(parent, "Add several neighbours")
        b = self.body
        ttk.Label(b, text="Add several neighbours", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(b, text=("One neighbour per line. To set an in-game rank, put it after a comma,\n"
                           "for example:  Sunny Acres, Elder"), justify="left",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 10))
        frame = ttk.Frame(b)
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, width=48, height=14, font=("Segoe UI", 10), relief="solid", borderwidth=1,
                            padx=8, pady=6, bg=C["entry"], highlightthickness=0, wrap="none")
        scroll = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        buttons = ttk.Frame(b)
        buttons.pack(anchor="e", pady=(14, 0), fill="x")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Add neighbours", style="Primary.TButton", command=self._ok).pack(side="right")
        self.text.focus_set()

    def _ok(self) -> None:
        rows = []
        for line in self.text.get("1.0", "end").splitlines():
            if not line.strip():
                continue
            name, _, rank = line.partition(",")
            rows.append((name.strip(), rank.strip()))
        self.result = rows
        self.destroy()
