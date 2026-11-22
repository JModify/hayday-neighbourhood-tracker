"""Main window: ties the database, the four tabs and the export/backup buttons together."""
from __future__ import annotations

import os
import sys
import tkinter as tk
import traceback
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import export
from .db import Database, default_db_path
from .scoring import week_results
from .ui_common import apply_theme, enable_mousewheel, make_window_icon
from .ui_dialogs import SettingsDialog
from .ui_monday import MondayTab
from .ui_neighbours import NeighboursTab
from .ui_overview import OverviewTab
from .ui_rankings import RankingsTab
from .util import fmt_date, most_recent_monday, week_choices

TITLE = "Hay Day Neighbourhood Tracker"


class App:
    def __init__(self, db_path: str | os.PathLike | None = None):
        self.db = Database(db_path or default_db_path())
        self.settings = self.db.load_settings()
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.report_callback_exception = self._report_error
        apply_theme(self.root)
        make_window_icon(self.root)
        enable_mousewheel(self.root)
        self._size_window()

        self.week = self.latest_monday()
        self._build_banner()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(0, 4))
        self.overview = OverviewTab(self.notebook, self)
        self.monday = MondayTab(self.notebook, self)
        self.neighbours = NeighboursTab(self.notebook, self)
        self.rankings = RankingsTab(self.notebook, self)
        self.tabs = {"overview": self.overview, "monday": self.monday,
                     "neighbours": self.neighbours, "rankings": self.rankings}
        titles = {"overview": "Overview", "monday": "Monday Update",
                  "neighbours": "Neighbours", "rankings": "Rankings"}
        for key, frame in self.tabs.items():
            self.notebook.add(frame, text=titles[key])
        self._build_footer()

        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_all()
        self.show_tab("monday")        # the weekly job is what you open the app for

    # --------------------------------------------------------------- window
    def _size_window(self) -> None:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(1280, sw - 60), min(840, sh - 110)
        self.root.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 3, 0)}")
        self.root.minsize(min(1100, w), min(640, h))

    def _build_banner(self) -> None:
        banner = ttk.Frame(self.root, style="Banner.TFrame", padding=(22, 12))
        banner.pack(fill="x", pady=(0, 6))
        text = ttk.Frame(banner, style="Banner.TFrame")
        text.pack(side="left")
        ttk.Label(text, text=f"🌾  {TITLE}", style="Banner.TLabel").pack(anchor="w")
        ttk.Label(text, text="Weekly progress for every neighbour, in one place", style="BannerSub.TLabel").pack(anchor="w")
        tools = ttk.Frame(banner, style="Banner.TFrame")
        tools.pack(side="right")
        menu_button = ttk.Menubutton(tools, text="Export CSV", style="Banner.TMenubutton")
        menu = tk.Menu(menu_button, tearoff=False)
        menu.add_command(label="All weekly entries and results…", command=self.export_history)
        menu.add_command(label="Selected week's rankings…", command=self.export_rankings)
        menu_button["menu"] = menu
        menu_button.pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Back up database…", style="Banner.TButton", command=self.backup).pack(side="left")

    def _build_footer(self) -> None:
        foot = ttk.Frame(self.root, padding=(18, 2, 18, 8))
        foot.pack(fill="x")
        ttk.Label(foot, text=f"Data file: {self.db.path}", style="Small.TLabel").pack(side="left")
        ttk.Button(foot, text="Open data folder", style="Nav.TButton", command=self.open_data_folder).pack(side="right")

    # ------------------------------------------------------------ week state
    def latest_monday(self) -> date:
        return most_recent_monday()

    def data_weeks(self) -> list[date]:
        return self.db.entry_dates()

    def week_options(self) -> list[date]:
        return week_choices(self.latest_monday(), self.data_weeks())

    def request_week(self, week: date) -> bool:
        """Switch every tab to ``week``, first dealing with unsaved typing in Monday Update."""
        if week != self.week and not self.monday.confirm_leave():
            self._refresh_pickers()
            return False
        self.week = week
        self.refresh_all(reload_monday=True)
        if self.notebook.select() == str(self.monday):
            self.monday.focus_first_empty()
        return True

    def _refresh_pickers(self) -> None:
        for tab in (self.overview, self.monday, self.rankings):
            tab.picker.refresh()

    def show_tab(self, name: str) -> None:
        self.notebook.select(self.tabs[name])

    def open_week_in_monday(self, week: date) -> None:
        if self.request_week(week):
            self.show_tab("monday")

    # ------------------------------------------------------------- refreshing
    def refresh_all(self, reload_monday: bool = False) -> None:
        if reload_monday or self.monday.week is None:
            self.monday.load_week(self.week)
        self.overview.refresh()
        self.rankings.refresh()
        self.neighbours.refresh()
        self._refresh_pickers()

    def data_changed(self, source=None) -> None:
        """Weekly numbers changed (saved from Monday Update, or an actual amount was supplied)."""
        if source is not self.monday:
            self.monday.reload_keeping_drafts()
        self.overview.refresh()
        self.rankings.refresh()
        self.neighbours.refresh()
        self._refresh_pickers()

    def neighbours_changed(self) -> None:
        """The roster changed: keep what has been typed in Monday Update and refresh the rest."""
        self.monday.reload_keeping_drafts()
        self.overview.refresh()
        self.rankings.refresh()
        self.neighbours.refresh()

    def _tab_changed(self, _event=None) -> None:
        current = self.notebook.select()
        if current == str(self.monday):
            if not self.monday.has_unsaved():
                self.monday.focus_first_empty()
        elif current == str(self.overview):
            self.overview.refresh()
        elif current == str(self.rankings):
            self.rankings.refresh()

    # ---------------------------------------------------------------- actions
    def edit_settings(self) -> None:
        result = SettingsDialog(self.root, self.settings).show()
        if result is None:
            return
        self.db.save_settings(result)
        self.settings = result
        self.monday.reload_keeping_drafts()
        self.overview.refresh()
        self.rankings.refresh()
        self.neighbours.refresh()

    def _save_path(self, title: str, default: str, kind: str, ext: str) -> str | None:
        docs = Path.home() / "Documents"
        return filedialog.asksaveasfilename(
            parent=self.root, title=title, initialfile=default, defaultextension=ext,
            initialdir=str(docs if docs.exists() else Path.home()), filetypes=[(kind, f"*{ext}"), ("All files", "*.*")]) or None

    def export_history(self) -> None:
        path = self._save_path("Export all weekly entries", f"HayDayTracker-history-{datetime.now():%Y%m%d}.csv",
                               "CSV files", ".csv")
        if not path:
            return
        try:
            count = export.export_history(self.db.load_dataset(), self.settings, path)
        except OSError as exc:
            messagebox.showerror("Export failed", f"Could not write the file.\n\n{exc}", parent=self.root)
            return
        messagebox.showinfo("Export complete", f"Exported {count} weekly entries to:\n{path}", parent=self.root)

    def export_rankings(self) -> None:
        path = self._save_path("Export this week's rankings", f"HayDayTracker-rankings-{self.week.isoformat()}.csv",
                               "CSV files", ".csv")
        if not path:
            return
        try:
            results = week_results(self.db.load_dataset(), self.week, self.settings)
            count = export.export_rankings(results, self.week, self.settings, path)
        except OSError as exc:
            messagebox.showerror("Export failed", f"Could not write the file.\n\n{exc}", parent=self.root)
            return
        messagebox.showinfo("Export complete", f"Exported {count} neighbours for {fmt_date(self.week)} to:\n{path}",
                            parent=self.root)

    def backup(self) -> None:
        path = self._save_path("Save a database backup", f"HayDayTracker-backup-{datetime.now():%Y%m%d-%H%M}.sqlite",
                               "SQLite backup", ".sqlite")
        if not path:
            return
        try:
            self.db.backup_to(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Backup failed", f"Could not save the backup.\n\n{exc}", parent=self.root)
            return
        messagebox.showinfo("Backup saved", f"Backup saved to:\n{path}\n\nTo restore it later, see the README.",
                            parent=self.root)

    def open_data_folder(self) -> None:
        try:
            os.startfile(str(self.db.path.parent))      # Windows only, which is the target platform
        except (AttributeError, OSError) as exc:
            messagebox.showinfo("Data folder", f"The data lives in:\n{self.db.path.parent}\n\n({exc})", parent=self.root)

    # ----------------------------------------------------------------- errors
    def _report_error(self, exc_type, exc, tb) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log = self.db.path.parent / "error.log"
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n{detail}\n")
            where = f"\n\nDetails were saved to:\n{log}"
        except OSError:
            where = ""
        messagebox.showerror("Something went wrong", f"{exc_type.__name__}: {exc}{where}", parent=self.root)

    # ---------------------------------------------------------------- closing
    def close(self) -> None:
        if not self.monday.confirm_leave():
            return
        self.db.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    db_path = None
    if "--db" in argv:                    # handy for trying things out without touching real data
        db_path = argv[argv.index("--db") + 1]
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp text on high-DPI screens
    except Exception:
        pass
    try:
        App(db_path).run()
    except Exception as exc:  # startup failures happen before the window exists
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(TITLE, f"The tracker could not start.\n\n{exc}")
        except tk.TclError:
            print(f"Could not start: {exc}", file=sys.stderr)
        raise
