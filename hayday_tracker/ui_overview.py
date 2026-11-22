"""The Overview tab: how the neighbourhood did in the selected week."""
from __future__ import annotations

from datetime import timedelta
from tkinter import ttk

from .scoring import DONATIONS, LEVELS, NURTURE, RESET, WeekSummary, summarise, week_results
from .ui_common import C, FONT, ScrollFrame, WeekPicker, make_card
from .util import fmt_date, fmt_int, fmt_period, fmt_signed

CARD_TITLES = {LEVELS: "Levels gained", NURTURE: "Nurture points earned", DONATIONS: "Donations made"}


class OverviewTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(20, 14, 20, 12))
        self.app = app
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
        ttk.Label(left, text="Overview", style="Title.TLabel").pack(anchor="w")
        self.period = ttk.Label(left, text="", style="Heading.TLabel")
        self.period.pack(anchor="w", pady=(2, 0))
        right = ttk.Frame(top)
        right.pack(side="right", anchor="n", pady=6)
        ttk.Label(right, text="Reporting Monday (✓ = has data)", style="Small.TLabel").pack(anchor="e")
        self.picker = WeekPicker(right, self.app)
        self.picker.pack(anchor="e", pady=(2, 0))

        # A prominent way into the weekly routine.
        cta_outer, cta = make_card(page, padding=12)
        cta_outer.pack(fill="x", pady=(8, 8))
        self.cta_text = ttk.Label(cta, text="", style="Card.TLabel", font=(FONT, 11))
        self.cta_text.pack(side="left")
        ttk.Button(cta, text="Open Monday Update", style="Primary.TButton",
                   command=lambda: self.app.open_week_in_monday(self.app.week)).pack(side="right")

        cards = ttk.Frame(page)
        cards.pack(fill="x")
        for i in range(4):
            cards.columnconfigure(i, weight=1, uniform="cards")
        self.card_widgets = {}
        for i, key in enumerate(("coverage", LEVELS, NURTURE, DONATIONS)):
            outer, inner = make_card(cards, padding=14)
            outer.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            title = {"coverage": "Reporting coverage"}.get(key, CARD_TITLES.get(key))
            ttk.Label(inner, text=title.upper(), style="CardMuted.TLabel", font=(FONT, 9, "bold")).pack(anchor="w")
            big = ttk.Label(inner, text="—", style="Big.TLabel")
            big.pack(anchor="w", pady=(2, 2))
            delta = ttk.Label(inner, text="", style="Card.TLabel", wraplength=180, justify="left")
            delta.pack(anchor="w")
            partial = ttk.Label(inner, text="", style="CardWarn.TLabel", wraplength=180, justify="left")
            partial.pack(anchor="w", pady=(2, 0))
            self.card_widgets[key] = (big, delta, partial)
        cards.bind("<Configure>", self._wrap_cards)

        lower = ttk.Frame(page)
        lower.pack(fill="both", expand=True, pady=(10, 0))
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        lower.rowconfigure(0, weight=1)

        o1, recent = make_card(lower, padding=12)
        o1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(recent, text="Recent weeks", style="CardHeading.TLabel").pack(anchor="w")
        cols = ("week", "entered", "levels", "nurture", "donations", "score")
        self.recent = ttk.Treeview(recent, columns=cols, show="headings", height=6, selectmode="none")
        for col, text, width, anchor in (("week", "Week (Monday)", 125, "w"), ("entered", "Entered", 70, "e"),
                                         ("levels", "Levels gained", 105, "e"), ("nurture", "Nurture", 80, "e"),
                                         ("donations", "Donations", 85, "e"), ("score", "Avg score", 80, "e")):
            self.recent.heading(col, text=text, anchor=anchor)
            self.recent.column(col, width=width, anchor=anchor)
        self.recent.pack(fill="both", expand=True, pady=(6, 4))
        ttk.Label(recent, text="* covers only part of the roster, so the total is not like-for-like.",
                  style="CardMuted.TLabel", font=(FONT, 9)).pack(anchor="w")

        right_col = ttk.Frame(lower)
        right_col.grid(row=0, column=1, sticky="nsew")
        right_col.columnconfigure(0, weight=1)
        o2, top3 = make_card(right_col, padding=12)
        o2.grid(row=0, column=0, sticky="ew")
        ttk.Label(top3, text="Top contributors", style="CardHeading.TLabel").pack(anchor="w")
        self.top_text = ttk.Label(top3, text="", style="Card.TLabel", justify="left", wraplength=360)
        self.top_text.pack(anchor="w", pady=(4, 0))
        o3, attention = make_card(right_col, padding=12)
        o3.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(attention, text="Needs attention", style="CardHeading.TLabel").pack(anchor="w")
        self.attention_text = ttk.Label(attention, text="", style="Card.TLabel", justify="left", wraplength=360)
        self.attention_text.pack(anchor="w", pady=(4, 0))

    def _wrap_cards(self, event) -> None:
        wrap = max(120, event.width // 4 - 44)
        for _big, delta, partial in self.card_widgets.values():
            delta.configure(wraplength=wrap)
            partial.configure(wraplength=wrap)

    # ------------------------------------------------------------------- data
    def refresh(self) -> None:
        app, week = self.app, self.app.week
        ds = app.db.load_dataset()
        settings = app.settings
        results = week_results(ds, week, settings)
        this = summarise(week, results)
        prev_week = week - timedelta(days=7)
        prev = summarise(prev_week, week_results(ds, prev_week, settings))
        self.picker.refresh()
        self.period.configure(text=f"Reporting period: {fmt_period(week)}")

        entered = f"{this.complete} of {this.roster} neighbours entered" if this.roster else "No neighbours yet"
        self.cta_text.configure(text=f"Monday update for {fmt_date(week, weekday=False)}:  {entered}"
                                     + (f"  ·  {this.partial} partly entered" if this.partial else ""))

        # Coverage card
        big, delta, partial = self.card_widgets["coverage"]
        big.configure(text=f"{this.complete} / {this.roster}")
        pct = f"{round(100 * this.complete / this.roster)}% of the roster fully entered" if this.roster else "Add neighbours to begin"
        delta.configure(text=pct + (f"\nLast week: {prev.complete} / {prev.roster}" if prev.roster else ""),
                        style="Card.TLabel")
        partial.configure(text=(f"{this.partial} partly entered" if this.partial else "")
                          + ("" if not this.partial or this.roster - this.complete - this.partial <= 0 else ", ")
                          + (f"{this.roster - this.complete - this.partial} not started"
                             if this.roster - this.complete - this.partial > 0 else ""))

        for key in (LEVELS, NURTURE, DONATIONS):
            big, delta, partial = self.card_widgets[key]
            n, total = this.counts[key], this.totals[key]
            if n == 0:
                big.configure(text="—")
                delta.configure(text="No usable figures yet this week", style="CardMuted.TLabel")
                partial.configure(text=self._reason_for_nothing(this, key))
                continue
            big.configure(text=fmt_int(total))
            if prev.counts[key] == 0:
                delta.configure(text="No previous week to compare with", style="CardMuted.TLabel")
            else:
                diff = total - prev.totals[key]
                arrow, style = ("▲", "CardGood.TLabel") if diff > 0 else (("▼", "CardBad.TLabel") if diff < 0
                                                                           else ("●", "CardMuted.TLabel"))
                delta.configure(text=f"{arrow} {fmt_signed(diff)} vs last week ({fmt_int(prev.totals[key])})",
                                style=style)
            notes = []
            if this.is_partial(key):
                notes.append(f"Partial: covers {n} of {this.roster} neighbours")
            if prev.counts[key] and prev.is_partial(key) and (this.is_partial(key) or prev.counts[key] != n):
                notes.append(f"Last week covered {prev.counts[key]} of {prev.roster}, so the change is not like-for-like")
            partial.configure(text="\n".join(notes))

        self._fill_recent(ds, settings, week)
        self._fill_top(results)
        self._fill_attention(results)

    @staticmethod
    def _reason_for_nothing(this: WeekSummary, key: str) -> str:
        if this.roster == 0:
            return ""
        return "Partial: covers 0 of %d neighbours" % this.roster

    def _fill_recent(self, ds, settings, week) -> None:
        self.recent.delete(*self.recent.get_children())
        for i in range(8):
            w = week - timedelta(days=7 * i)
            if w not in ds.entries:
                continue
            s = summarise(w, week_results(ds, w, settings))
            scores = [r.score for r in s.results if r.score is not None]
            avg = f"{sum(scores) / len(scores):.1f}" if scores else "—"

            def cell(key):
                if s.counts[key] == 0:
                    return "—"
                return fmt_int(s.totals[key]) + ("*" if s.is_partial(key) else "")
            self.recent.insert("", "end", values=(fmt_date(w), f"{s.complete} / {s.roster}", cell(LEVELS),
                                                  cell(NURTURE), cell(DONATIONS), avg))

    def _fill_top(self, results) -> None:
        scored = sorted((r for r in results if r.position is not None), key=lambda r: (r.position, r.neighbour.farm_name.lower()))
        if not scored:
            self.top_text.configure(text="No scores yet. A score needs this week's numbers and the previous "
                                         "Monday's as a baseline.")
            return
        lines = [f"{r.position}.  {r.neighbour.label}  —  {r.score:.2f}" for r in scored[:3]]
        # include any further ties for third place so nobody is left out
        cutoff = scored[min(2, len(scored) - 1)].position
        extra = [r for r in scored[3:] if r.position == cutoff]
        lines += [f"{r.position}.  {r.neighbour.label}  —  {r.score:.2f}" for r in extra]
        self.top_text.configure(text="\n".join(lines))

    def _fill_attention(self, results) -> None:
        items = []
        for r in sorted(results, key=lambda r: r.neighbour.farm_name.lower()):
            name = r.neighbour.farm_name
            if r.entry is None:
                items.append(f"{name}: not entered yet")
            elif not r.entry.complete:
                items.append(f"{name}: partly entered")
            elif any(r.metrics[k].status == RESET for k in (NURTURE, DONATIONS)):
                items.append(f"{name}: a counter dropped (supply the actual amount in Rankings)")
            elif r.flags_text and "level decreased" in r.flags_text:
                items.append(f"{name}: farm level is lower than last week")
        shown = items[:8]
        text = "\n".join("• " + i for i in shown) if shown else "Nothing to flag. Every neighbour is entered and consistent."
        if len(items) > len(shown):
            text += f"\n…and {len(items) - len(shown)} more"
        self.attention_text.configure(text=text)
