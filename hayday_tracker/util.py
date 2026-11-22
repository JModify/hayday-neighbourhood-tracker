"""Dates, number parsing and display formatting shared across the app."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

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
CUTOFF = time(18, 0)        # Hay Day resets its stats at 6 PM Monday, Brisbane time

_clock = lambda: datetime.now(BRISBANE)       # noqa: E731  (replaceable so tests can set the time)


def set_clock(fn=None) -> None:
    """Replace the source of 'now' (for tests). ``None`` restores the real clock."""
    global _clock
    _clock = fn or (lambda: datetime.now(BRISBANE))


def now_brisbane() -> datetime:
    """The current date and time in Brisbane, whatever time zone the PC is set to."""
    return _clock()


def today_brisbane() -> date:
    return now_brisbane().date()


def cutoff_for(reporting_monday: date) -> datetime:
    """When entry for a reporting Monday closes: 6:00 PM that Monday, Brisbane time."""
    return datetime.combine(reporting_monday, CUTOFF, tzinfo=BRISBANE)


def is_week_locked(reporting_monday: date, now: datetime | None = None) -> bool:
    """True once the 6 PM cutoff for that reporting Monday has passed."""
    return (now or now_brisbane()) >= cutoff_for(reporting_monday)


def current_reporting_monday(now: datetime | None = None) -> date:
    """The reporting Monday that is open for entry right now.

    It is the next Monday whose 6 PM cutoff has not yet passed. So on Sunday it is tomorrow's Monday,
    on Monday before 6 PM it is today, and from 6 PM Monday it becomes the Monday a week later.
    """
    now = now or now_brisbane()
    monday = most_recent_monday(now.date())
    return monday + timedelta(days=7) if now >= cutoff_for(monday) else monday


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


def fmt_cutoff(reporting_monday: date) -> str:
    """e.g. 'Mon 17 Nov 2026, 6:00 PM'"""
    return f"{fmt_date(reporting_monday)}, 6:00 PM"


def fmt_remaining(delta: timedelta) -> str:
    minutes = max(int(delta.total_seconds() // 60), 0)
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours and days < 3:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins and not days:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts) or "less than a minute"


def week_choices(current: date, data_dates: list[date] | None = None) -> list[date]:
    """Mondays offered in the week pickers, newest first: the open week plus every week that has data.

    Closed weeks cannot be changed, so empty ones from the past are not offered.
    """
    return sorted({current, *(data_dates or [])}, reverse=True)


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
