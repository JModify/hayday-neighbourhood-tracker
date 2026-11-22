"""Plain data classes shared by the database, scoring and interface layers."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

MODE_WEEKLY = "weekly"
MODE_CUMULATIVE = "cumulative"
MODES = (MODE_WEEKLY, MODE_CUMULATIVE)


@dataclass(frozen=True)
class Neighbour:
    id: int
    farm_name: str
    game_rank: str
    player_tag: str
    notes: str
    first_week: date          # Monday of the week they joined the roster
    archived_on: date | None

    @property
    def archived(self) -> bool:
        return self.archived_on is not None

    @property
    def label(self) -> str:
        return f"{self.farm_name} (archived)" if self.archived else self.farm_name


@dataclass(frozen=True)
class Entry:
    neighbour_id: int
    reporting_date: date
    farm_level: int | None
    nurture: int | None
    donations: int | None
    nurture_actual: int | None = None      # amount really earned after a counter reset
    donations_actual: int | None = None

    @property
    def complete(self) -> bool:
        return None not in (self.farm_level, self.nurture, self.donations)


@dataclass(frozen=True)
class EntryInput:
    neighbour_id: int
    farm_level: int | None
    nurture: int | None
    donations: int | None
    nurture_actual: int | None = None
    donations_actual: int | None = None


@dataclass
class Dataset:
    neighbours: dict[int, Neighbour] = field(default_factory=dict)
    entries: dict[date, dict[int, Entry]] = field(default_factory=dict)

    def dates(self) -> list[date]:
        return sorted(self.entries)


@dataclass
class Settings:
    nurture_mode: str = MODE_CUMULATIVE
    donations_mode: str = MODE_CUMULATIVE
    weight_nurture: float = 45.0
    weight_donations: float = 45.0
    weight_levels: float = 10.0
    target_nurture: float = 100.0
    target_donations: float = 20.0
    target_levels: float = 1.0

    def problems(self) -> list[str]:
        out: list[str] = []
        if self.nurture_mode not in MODES or self.donations_mode not in MODES:
            out.append("Each counter must be weekly or cumulative.")
        weights = (self.weight_nurture, self.weight_donations, self.weight_levels)
        targets = (self.target_nurture, self.target_donations, self.target_levels)
        if not all(math.isfinite(w) and w >= 0 for w in weights):
            out.append("Weights must be numbers of zero or more.")
        elif abs(sum(weights) - 100) > 1e-6:
            out.append(f"Weights must add up to 100% (they add up to {sum(weights):g}%).")
        if not all(math.isfinite(t) and t > 0 for t in targets):
            out.append("Weekly targets must be numbers greater than zero.")
        return out
