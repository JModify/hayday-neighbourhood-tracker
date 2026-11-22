"""Weekly metrics, contribution scores and leaderboard positions.

Nothing here touches the database or the screen, so it is easy to test.

How a week is worked out
------------------------
* Farm level: the difference from the previous Monday's entry.
* Nurture and donations: used directly when set to *weekly*; otherwise the
  difference from the previous Monday's entry (*cumulative*).
* A cumulative counter that drops is flagged. If an actual amount was supplied
  it is used; otherwise that metric is missing.
* Score: for each metric, ``min(result / target, 1) * weight``, added together.
  Any required metric (weight above zero) that is missing gives no score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import MODE_WEEKLY, Dataset, Entry, Neighbour, Settings
from .util import fmt_date, fmt_int

LEVELS, NURTURE, DONATIONS, DERBY = "levels", "nurture", "donations", "derby"
METRICS = (NURTURE, DONATIONS, DERBY, LEVELS)
COUNTERS = (NURTURE, DONATIONS, DERBY)     # metrics entered as a number that can be weekly or cumulative
LABELS = {LEVELS: "Levels gained", NURTURE: "Nurture points", DONATIONS: "Donations", DERBY: "Derby points"}
SHORT_LABELS = {LEVELS: "Levels", NURTURE: "Nurture", DONATIONS: "Donations", DERBY: "Derby"}

OK, OVERRIDE, NOT_ENTERED, NO_BASELINE, RESET = (
    "ok", "override", "not_entered", "no_baseline", "reset")

_FLAG_TEXT = {OVERRIDE: "actual supplied", NOT_ENTERED: "not entered",
              NO_BASELINE: "no baseline", RESET: "counter reset"}
_CELL_TEXT = {NOT_ENTERED: "Not entered", NO_BASELINE: "No baseline", RESET: "Counter reset ⚠"}


@dataclass(frozen=True)
class Metric:
    key: str
    value: int | None
    status: str
    note: str = ""
    current: int | None = None     # raw figure entered this week
    previous: int | None = None    # raw figure from the previous Monday

    @property
    def usable(self) -> bool:
        return self.value is not None

    @property
    def text(self) -> str:
        """What the tables show: a number (including a true 0) or the reason it is missing."""
        if self.value is None:
            return _CELL_TEXT[self.status]
        return fmt_int(self.value) + ("*" if self.status == OVERRIDE else "")

    @property
    def flag(self) -> str:
        if self.status == OK and self.key == LEVELS and self.value is not None and self.value < 0:
            return "level decreased"
        return _FLAG_TEXT.get(self.status, "")


@dataclass(frozen=True)
class Part:
    """One line of the score breakdown."""
    key: str
    value: int | None
    target: float
    weight: float
    fraction: float | None     # capped at 1.0 (100% of target)
    points: float | None


@dataclass
class WeekResult:
    neighbour: Neighbour
    week: date
    entry: Entry | None
    previous_entry: Entry | None
    metrics: dict[str, Metric]
    parts: dict[str, Part]
    score: float | None
    required: tuple[str, ...]
    position: int | None = None
    previous_position: int | None = None

    @property
    def position_change(self) -> int | None:
        """Positive means the neighbour moved up the leaderboard."""
        if self.position is None or self.previous_position is None:
            return None
        return self.previous_position - self.position

    @property
    def missing_required(self) -> list[str]:
        return [k for k in self.required if not self.metrics[k].usable]

    @property
    def entered(self) -> bool:
        """All four values (farm level, Nurture, donations and Derby) are in, whatever the score weights are."""
        return self.entry is not None and self.entry.complete

    @property
    def flags_text(self) -> str:
        if self.entry is None:
            return "No entry for this week"
        # A metric that is not scored (weight 0) and was simply not entered is not worth a warning.
        bits = [f"{SHORT_LABELS[k]}: {self.metrics[k].flag}" for k in METRICS
                if self.metrics[k].flag and not (k not in self.required and self.metrics[k].status == NOT_ENTERED)]
        return "; ".join(bits)


@dataclass
class WeekSummary:
    week: date
    roster: int
    complete: int
    partial: int
    totals: dict[str, int]
    counts: dict[str, int]            # neighbours contributing to each total
    results: list[WeekResult] = field(default_factory=list)

    def is_partial(self, key: str) -> bool:
        return self.counts[key] < self.roster


# ----------------------------------------------------------------- metric maths
def _levels_metric(entry: Entry | None, prev: Entry | None, week: date) -> Metric:
    cur = entry.farm_level if entry else None
    if cur is None:
        return Metric(LEVELS, None, NOT_ENTERED,
                      "Farm level not entered" if entry else "No entry for this week")
    base = prev.farm_level if prev else None
    if base is None:
        why = (f"No entry for {fmt_date(week - timedelta(days=7))}" if prev is None
               else "Farm level was blank last week")
        return Metric(LEVELS, None, NO_BASELINE, why, current=cur)
    gain = cur - base
    note = "Farm level is lower than last week, so check for a typing slip" if gain < 0 else ""
    return Metric(LEVELS, gain, OK, note, cur, base)


def _counter_metric(key: str, mode: str, entry: Entry | None, prev: Entry | None, week: date) -> Metric:
    label = SHORT_LABELS[key]
    cur = getattr(entry, key) if entry else None
    if cur is None:
        return Metric(key, None, NOT_ENTERED,
                      f"{label} not entered" if entry else "No entry for this week")
    if mode == MODE_WEEKLY:
        return Metric(key, cur, OK, "", cur, None)
    base = getattr(prev, key) if prev else None
    if base is None:
        why = (f"No entry for {fmt_date(week - timedelta(days=7))}" if prev is None
               else f"{label} was blank last week")
        return Metric(key, None, NO_BASELINE, why, current=cur)
    diff = cur - base
    if diff >= 0:
        return Metric(key, diff, OK, "", cur, base)
    actual = getattr(entry, key + "_actual")
    drop = f"Total dropped from {base:,} to {cur:,}"
    if actual is not None:
        return Metric(key, actual, OVERRIDE, f"{drop}; using the actual amount you supplied", cur, base)
    return Metric(key, None, RESET, f"{drop}. Counter reset? Supply the actual amount earned if you know it",
                  cur, base)


def _score(settings: Settings, metrics: dict[str, Metric]) -> tuple[dict[str, Part], float | None, tuple[str, ...]]:
    parts: dict[str, Part] = {}
    for key in METRICS:
        target = getattr(settings, f"target_{key}")
        weight = getattr(settings, f"weight_{key}")
        value = metrics[key].value
        fraction = None if value is None else max(0.0, min(1.0, value / target))
        points = None if fraction is None else weight * fraction
        parts[key] = Part(key, value, target, weight, fraction, points)
    required = tuple(k for k in METRICS if parts[k].weight > 0)
    if any(parts[k].points is None for k in required):
        return parts, None, required
    # Rounded to 2 decimal places so what is shown is exactly what is ranked.
    return parts, round(sum(p.points for p in parts.values() if p.points is not None), 2), required


# ---------------------------------------------------------------- week results
def roster_ids(ds: Dataset, week: date) -> set[int]:
    """Who counts for a week: anyone with an entry, plus active neighbours who had joined by then.

    Archived neighbours stay in the weeks where they have results but do not
    appear as 'missing' in weeks without any.
    """
    ids = set(ds.entries.get(week, {}))
    for n in ds.neighbours.values():
        if not n.archived and n.first_week <= week:
            ids.add(n.id)
    return ids


def _raw_results(ds: Dataset, week: date, settings: Settings) -> list[WeekResult]:
    prev_week = week - timedelta(days=7)
    this_entries = ds.entries.get(week, {})
    prev_entries = ds.entries.get(prev_week, {})
    out = []
    for nid in roster_ids(ds, week):
        entry, prev = this_entries.get(nid), prev_entries.get(nid)
        metrics = {LEVELS: _levels_metric(entry, prev, week)}
        for key in COUNTERS:
            metrics[key] = _counter_metric(key, getattr(settings, f"{key}_mode"), entry, prev, week)
        parts, score, required = _score(settings, metrics)
        out.append(WeekResult(ds.neighbours[nid], week, entry, prev, metrics, parts, score, required))
    out.sort(key=lambda r: r.neighbour.farm_name.lower())
    return out


def assign_positions(results: list[WeekResult]) -> None:
    """Leaderboard positions by score. Tied scores share a position (1, 1, 3, ...)."""
    scored = [r.score for r in results if r.score is not None]
    for r in results:
        r.position = None if r.score is None else 1 + sum(1 for s in scored if s > r.score)


def week_results(ds: Dataset, week: date, settings: Settings) -> list[WeekResult]:
    """Every neighbour's results for ``week``, with leaderboard positions and movement."""
    results = _raw_results(ds, week, settings)
    assign_positions(results)
    previous = _raw_results(ds, week - timedelta(days=7), settings)
    assign_positions(previous)
    before = {r.neighbour.id: r.position for r in previous}
    for r in results:
        r.previous_position = before.get(r.neighbour.id)
    return results


def neighbour_history(ds: Dataset, neighbour_id: int, settings: Settings) -> list[WeekResult]:
    """One neighbour's results for every week they have an entry, newest first."""
    weeks = sorted((d for d, rows in ds.entries.items() if neighbour_id in rows), reverse=True)
    out = []
    for week in weeks:
        for r in week_results(ds, week, settings):
            if r.neighbour.id == neighbour_id:
                out.append(r)
    return out


def summarise(week: date, results: list[WeekResult]) -> WeekSummary:
    totals = {k: 0 for k in METRICS}
    counts = {k: 0 for k in METRICS}
    for r in results:
        for k in METRICS:
            m = r.metrics[k]
            if m.usable:
                totals[k] += m.value
                counts[k] += 1
    complete = sum(1 for r in results if r.entered)
    partial = sum(1 for r in results if r.entry is not None and not r.entered)
    return WeekSummary(week, len(results), complete, partial, totals, counts, results)
