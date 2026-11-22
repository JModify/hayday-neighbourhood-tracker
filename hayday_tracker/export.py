"""CSV export. Files open cleanly in Excel (UTF-8 with a byte-order mark)."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from .models import Dataset, Settings
from .scoring import DONATIONS, LEVELS, METRICS, NURTURE, WeekResult, week_results
from .util import fmt_num


def _safe(value):
    """Stop spreadsheet programs treating a typed name like '=SUM(A1)' as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _blank(value):
    return "" if value is None else value


def _change_text(r: WeekResult) -> str:
    change = r.position_change
    if r.position is None:
        return ""
    if r.previous_position is None:
        return "new"
    return "0" if change == 0 else f"{change:+d}"


def _write(path: str | Path, header: list[str], rows: list[list]) -> int:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return len(rows)


def _result_columns(r: WeekResult, settings: Settings) -> list:
    m = r.metrics
    return [
        _blank(m[LEVELS].value), _blank(m[NURTURE].value), _blank(m[DONATIONS].value),
        "Insufficient data" if r.score is None else f"{r.score:.2f}",
        _blank(r.position), _change_text(r), r.flags_text,
    ]


def export_history(ds: Dataset, settings: Settings, path: str | Path) -> int:
    """Every saved weekly entry, with the calculated results beside the raw numbers."""
    header = ["Reporting date (Monday)", "Week start", "Week end", "Neighbour ID", "Farm name",
              "Status", "In-game rank", "Player tag", "Farm level", "Nurture (as entered)",
              "Donations (as entered)", "Nurture actual (after reset)", "Donations actual (after reset)",
              "Levels gained", "Nurture points", "Donations made", "Overall score",
              "Leaderboard position", "Position change", "Data notes"]
    rows = []
    for week in sorted(ds.entries):
        for r in week_results(ds, week, settings):
            e = r.entry
            if e is None:
                continue
            n = r.neighbour
            rows.append([week.isoformat(), (week - timedelta(days=7)).isoformat(),
                         (week - timedelta(days=1)).isoformat(), n.id, _safe(n.farm_name),
                         "Archived" if n.archived else "Active", _safe(n.game_rank), _safe(n.player_tag),
                         _blank(e.farm_level), _blank(e.nurture), _blank(e.donations),
                         _blank(e.nurture_actual), _blank(e.donations_actual)]
                        + _result_columns(r, settings))
    return _write(path, header, rows)


def export_rankings(results: list[WeekResult], week: date, settings: Settings, path: str | Path) -> int:
    """The Rankings table for one week, plus the score breakdown and active settings."""
    header = ["Reporting date (Monday)", "Leaderboard position", "Farm name", "In-game rank",
              "Levels gained", "Nurture points", "Donations made", "Overall score",
              "Position change", "Data notes",
              "Nurture points scored", "Donation points scored", "Level points scored",
              "Nurture mode", "Donations mode", "Weights N/D/L (%)", "Targets N/D/L"]
    weights = "/".join(fmt_num(getattr(settings, f"weight_{k}")) for k in METRICS)
    targets = "/".join(fmt_num(getattr(settings, f"target_{k}")) for k in METRICS)
    ordered = sorted(results, key=lambda r: (r.position is None, r.position or 0,
                                             r.neighbour.farm_name.lower()))
    rows = []
    for r in ordered:
        pts = [(_blank(None if r.parts[k].points is None else round(r.parts[k].points, 2)))
               for k in (NURTURE, DONATIONS, LEVELS)]
        rows.append([week.isoformat(), _blank(r.position), _safe(r.neighbour.farm_name), _safe(r.neighbour.game_rank),
                     _blank(r.metrics[LEVELS].value), _blank(r.metrics[NURTURE].value),
                     _blank(r.metrics[DONATIONS].value),
                     "Insufficient data" if r.score is None else f"{r.score:.2f}",
                     _change_text(r), r.flags_text, *pts,
                     settings.nurture_mode, settings.donations_mode, weights, targets])
    return _write(path, header, rows)
