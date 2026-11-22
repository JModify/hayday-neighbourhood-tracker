"""SQLite storage. Everything the app remembers lives in one database file."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .models import Dataset, Entry, EntryInput, Neighbour, Settings
from .util import is_monday, most_recent_monday, today_brisbane

APP_DIR_NAME = "HayDayTracker"
DB_FILE_NAME = "hayday_tracker.db"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS neighbours (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_name    TEXT NOT NULL,
    game_rank    TEXT NOT NULL DEFAULT '',
    player_tag   TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    first_week   TEXT NOT NULL,
    archived_on  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_neighbours_tag
    ON neighbours(player_tag) WHERE player_tag <> '';

CREATE TABLE IF NOT EXISTS weekly_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    neighbour_id      INTEGER NOT NULL REFERENCES neighbours(id) ON DELETE CASCADE,
    reporting_date    TEXT NOT NULL,
    farm_level        INTEGER CHECK (farm_level IS NULL OR farm_level >= 1),
    nurture           INTEGER CHECK (nurture IS NULL OR nurture >= 0),
    donations         INTEGER CHECK (donations IS NULL OR donations >= 0),
    nurture_actual    INTEGER CHECK (nurture_actual IS NULL OR nurture_actual >= 0),
    donations_actual  INTEGER CHECK (donations_actual IS NULL OR donations_actual >= 0),
    updated_at        TEXT NOT NULL,
    UNIQUE (neighbour_id, reporting_date)
);
CREATE INDEX IF NOT EXISTS ix_entries_date ON weekly_entries(reporting_date);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


class ValidationError(ValueError):
    """A problem with something the user typed; the message is shown as-is."""


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_DIR_NAME


def default_db_path() -> Path:
    return default_data_dir() / DB_FILE_NAME


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(text: str | None, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


def _row_to_neighbour(r: sqlite3.Row) -> Neighbour:
    return Neighbour(
        id=r["id"],
        farm_name=r["farm_name"],
        game_rank=r["game_rank"],
        player_tag=r["player_tag"],
        notes=r["notes"],
        first_week=date.fromisoformat(r["first_week"]),
        archived_on=date.fromisoformat(r["archived_on"]) if r["archived_on"] else None,
    )


def _row_to_entry(r: sqlite3.Row) -> Entry:
    return Entry(
        neighbour_id=r["neighbour_id"],
        reporting_date=date.fromisoformat(r["reporting_date"]),
        farm_level=r["farm_level"],
        nurture=r["nurture"],
        donations=r["donations"],
        nurture_actual=r["nurture_actual"],
        donations_actual=r["donations_actual"],
    )


class Database:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._prepare()

    def close(self) -> None:
        self.conn.close()

    def _prepare(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                "This database was made by a newer version of the tracker "
                f"(schema {version}); this copy understands schema {SCHEMA_VERSION}.")
        self.conn.executescript(SCHEMA)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    # ------------------------------------------------------------- neighbours
    def list_neighbours(self, include_archived: bool = True) -> list[Neighbour]:
        sql = "SELECT * FROM neighbours"
        if not include_archived:
            sql += " WHERE archived_on IS NULL"
        return [_row_to_neighbour(r) for r in self.conn.execute(sql + " ORDER BY farm_name COLLATE NOCASE")]

    def get_neighbour(self, neighbour_id: int) -> Neighbour | None:
        r = self.conn.execute("SELECT * FROM neighbours WHERE id = ?", (neighbour_id,)).fetchone()
        return _row_to_neighbour(r) if r else None

    @staticmethod
    def _validated(farm_name: str, game_rank: str, player_tag: str, notes: str) -> tuple[str, str, str, str]:
        name = _clean(farm_name, 60)
        if not name:
            raise ValidationError("Please enter the neighbour's farm name.")
        rank = _clean(game_rank, 30)
        tag = _clean(player_tag, 20).replace(" ", "").upper()
        note = (notes or "").strip()[:1000]
        return name, rank, tag, note

    def name_in_use(self, farm_name: str, exclude_id: int | None = None) -> bool:
        r = self.conn.execute(
            "SELECT 1 FROM neighbours WHERE farm_name = ? COLLATE NOCASE AND id <> ?",
            (_clean(farm_name, 60), exclude_id or -1)).fetchone()
        return r is not None

    def add_neighbour(self, farm_name: str, game_rank: str = "", player_tag: str = "",
                      notes: str = "", today: date | None = None) -> int:
        name, rank, tag, note = self._validated(farm_name, game_rank, player_tag, notes)
        first_week = most_recent_monday(today or today_brisbane())
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO neighbours (farm_name, game_rank, player_tag, notes, first_week) "
                    "VALUES (?, ?, ?, ?, ?)", (name, rank, tag, note, first_week.isoformat()))
        except sqlite3.IntegrityError:
            raise ValidationError(f"Another neighbour already has the player tag {tag}.") from None
        return int(cur.lastrowid)

    def update_neighbour(self, neighbour_id: int, farm_name: str, game_rank: str,
                         player_tag: str, notes: str) -> None:
        name, rank, tag, note = self._validated(farm_name, game_rank, player_tag, notes)
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE neighbours SET farm_name=?, game_rank=?, player_tag=?, notes=? WHERE id=?",
                    (name, rank, tag, note, neighbour_id))
        except sqlite3.IntegrityError:
            raise ValidationError(f"Another neighbour already has the player tag {tag}.") from None

    def archive_neighbour(self, neighbour_id: int, today: date | None = None) -> None:
        with self.conn:
            self.conn.execute("UPDATE neighbours SET archived_on=? WHERE id=?",
                              ((today or today_brisbane()).isoformat(), neighbour_id))

    def restore_neighbour(self, neighbour_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE neighbours SET archived_on=NULL WHERE id=?", (neighbour_id,))

    def entry_count(self, neighbour_id: int) -> tuple[int, date | None, date | None]:
        r = self.conn.execute(
            "SELECT COUNT(*), MIN(reporting_date), MAX(reporting_date) FROM weekly_entries "
            "WHERE neighbour_id = ?", (neighbour_id,)).fetchone()
        first = date.fromisoformat(r[1]) if r[1] else None
        last = date.fromisoformat(r[2]) if r[2] else None
        return r[0], first, last

    def delete_neighbour(self, neighbour_id: int) -> int:
        """Permanently remove a neighbour and all their weekly entries."""
        count = self.entry_count(neighbour_id)[0]
        with self.conn:
            self.conn.execute("DELETE FROM neighbours WHERE id = ?", (neighbour_id,))
        return count

    # ---------------------------------------------------------------- entries
    def load_dataset(self) -> Dataset:
        ds = Dataset()
        for r in self.conn.execute("SELECT * FROM neighbours"):
            n = _row_to_neighbour(r)
            ds.neighbours[n.id] = n
        for r in self.conn.execute("SELECT * FROM weekly_entries"):
            e = _row_to_entry(r)
            ds.entries.setdefault(e.reporting_date, {})[e.neighbour_id] = e
        return ds

    def entry_dates(self) -> list[date]:
        """Every reporting Monday that has at least one saved entry."""
        rows = self.conn.execute("SELECT DISTINCT reporting_date FROM weekly_entries ORDER BY 1").fetchall()
        return [date.fromisoformat(r[0]) for r in rows]

    def save_week(self, reporting_date: date, rows: Iterable[EntryInput]) -> tuple[int, int]:
        """Save every row in one transaction. Returns ``(saved, cleared)``.

        There is one entry per neighbour per reporting date, so saving again
        updates the existing record. A row with all three values blank removes
        any saved entry for that neighbour and week.
        """
        if not is_monday(reporting_date):
            raise ValidationError("The reporting date must be a Monday.")
        saved = cleared = 0
        stamp = _now_text()
        day = reporting_date.isoformat()
        with self.conn:  # one transaction: commits on success, rolls back on any error
            for row in rows:
                if row.farm_level is None and row.nurture is None and row.donations is None:
                    cur = self.conn.execute(
                        "DELETE FROM weekly_entries WHERE neighbour_id=? AND reporting_date=?",
                        (row.neighbour_id, day))
                    cleared += cur.rowcount
                    continue
                self.conn.execute(
                    """INSERT INTO weekly_entries
                         (neighbour_id, reporting_date, farm_level, nurture, donations,
                          nurture_actual, donations_actual, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(neighbour_id, reporting_date) DO UPDATE SET
                         farm_level=excluded.farm_level, nurture=excluded.nurture,
                         donations=excluded.donations, nurture_actual=excluded.nurture_actual,
                         donations_actual=excluded.donations_actual, updated_at=excluded.updated_at""",
                    (row.neighbour_id, day, row.farm_level, row.nurture, row.donations,
                     row.nurture_actual, row.donations_actual, stamp))
                saved += 1
        return saved, cleared

    def set_actual(self, neighbour_id: int, reporting_date: date, metric: str, value: int | None) -> None:
        """Record (or clear) the amount actually earned after a cumulative counter dropped."""
        column = {"nurture": "nurture_actual", "donations": "donations_actual"}[metric]
        with self.conn:
            cur = self.conn.execute(
                f"UPDATE weekly_entries SET {column}=?, updated_at=? "
                "WHERE neighbour_id=? AND reporting_date=?",
                (value, _now_text(), neighbour_id, reporting_date.isoformat()))
        if cur.rowcount == 0:
            raise ValidationError("There is no saved entry for that neighbour and week yet.")

    # --------------------------------------------------------------- settings
    def load_settings(self) -> Settings:
        stored = {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM settings")}
        s = Settings()
        for f in fields(Settings):
            if f.name not in stored:
                continue
            try:
                setattr(s, f.name, stored[f.name] if f.name.endswith("_mode") else float(stored[f.name]))
            except ValueError:
                pass
        return s if not s.problems() else Settings()

    def save_settings(self, s: Settings) -> None:
        problems = s.problems()
        if problems:
            raise ValidationError(" ".join(problems))
        with self.conn:
            for f in fields(Settings):
                self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                                  (f.name, str(getattr(s, f.name))))

    # ----------------------------------------------------------------- backup
    def backup_to(self, destination: str | os.PathLike) -> Path:
        """Write a consistent copy of the whole database to ``destination``."""
        dest = Path(destination)
        if dest.resolve() == self.path.resolve():
            raise ValidationError("Choose a different file from the live database.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()
        return dest
