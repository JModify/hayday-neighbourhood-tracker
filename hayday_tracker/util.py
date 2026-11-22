"""Dates, number parsing and display formatting shared across the app."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

try:  # The tz database is not guaranteed on Windows, so fall back safely.
    from zoneinfo import ZoneInfo

    BRISBANE = ZoneInfo("Australia/Brisbane")
except Exception:  # pragma: no cover - depends on the machine
    # Brisbane has not used daylight saving since 1992, so a fixed +10:00 offset is exact.
    BRISBANE = timezone(timedelta(hours=10), "AEST")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MAX_LEVEL = 1000
MAX_COUNT = 10 ** 12


# --------------------------------------------------------------------------- dates
def today_brisbane() -> date:
    """Today's date in Brisbane, regardless of the PC's own time zone."""
    return datetime.now(BRISBANE).date()


def most_recent_monday(today: date | None = None) -> date:
    """The Monday on or before ``today`` (Brisbane today by default)."""
    today = today or today_brisbane()
    return today - timedelta(days=today.weekday())


def prior_monday(monday: date) -> date:
    return monday - timedelta(days=7)


def is_monday(d: date) -> bool:
    return d.weekday() == 0


def fmt_date(d: date | None, weekday: bool = True) -> str:
    if d is None:
        return "—"
    text = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return f"{DAYS[d.weekday()]} {text}" if weekday else text


def fmt_day_month(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def fmt_period(reporting_monday: date) -> str:
    """The week that ended on the Sunday before the reporting Monday."""
    start = reporting_monday - timedelta(days=7)
    end = reporting_monday - timedelta(days=1)
    if start.year == end.year:
        return (f"{DAYS[start.weekday()]} {fmt_day_month(start)} – "
                f"{DAYS[end.weekday()]} {fmt_day_month(end)} {end.year}")
    return f"{fmt_date(start)} – {fmt_date(end)}"


def week_choices(latest: date, data_dates: list[date] | None = None, back_weeks: int = 104) -> list[date]:
    """Mondays offered in the week pickers, newest first."""
    data_dates = data_dates or []
    newest = max([latest] + data_dates)
    oldest = latest - timedelta(weeks=back_weeks)
    if data_dates:
        oldest = min(oldest, min(data_dates))
    out, d = [], newest
    while d >= oldest:
        out.append(d)
        d -= timedelta(days=7)
    return out


# --------------------------------------------------------------------------- numbers
_DIGITS = re.compile(r"\d+", re.ASCII)


def parse_count(text: str, minimum: int = 0, maximum: int = MAX_COUNT) -> tuple[int | None, str | None]:
    """Parse a whole number typed by the user.

    Returns ``(value, error)``. A blank box is ``(None, None)`` so that it stays
    distinct from a genuine zero.
    """
    cleaned = (text or "").strip().replace(",", "").replace(" ", "").replace(" ", "")
    if cleaned == "":
        return None, None
    if cleaned.startswith("-"):
        return None, "must not be negative"
    if not _DIGITS.fullmatch(cleaned):
        return None, "must be a whole number"
    value = int(cleaned)
    if value < minimum or value > maximum:
        return None, f"must be between {minimum:,} and {maximum:,}"
    return value, None


def fmt_int(n: int | None) -> str:
    return "—" if n is None else f"{n:,}"


def fmt_signed(n: int | None) -> str:
    if n is None:
        return "—"
    return "0" if n == 0 else f"{n:+,}"


def fmt_num(x: float) -> str:
    """Trim trailing zeros: 45.0 -> '45', 2.50 -> '2.5'."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_score(x: float | None) -> str:
    return "Insufficient data" if x is None else f"{x:.2f}"
