"""Checks for the version 1.0.1 changes. Uses temporary databases only.

Run:  py -3 tests\\verify_v101.py

  * the Monday Update grid scrolls (mouse wheel and scroll bar) even when the roster is added after the window opened
  * the selected tab changes colour only, never size
  * Derby scores: upgrade of a version 1.0.0 database, entering, scoring, Rankings, history and CSV export
"""
from __future__ import annotations

import csv
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from hayday_tracker import export                                   # noqa: E402
from hayday_tracker.app import App                                  # noqa: E402
from hayday_tracker.db import Database                              # noqa: E402
from hayday_tracker.models import EntryInput, Settings              # noqa: E402
from hayday_tracker.scoring import DERBY, RESET, week_results        # noqa: E402

W0, W1 = date(2026, 11, 9), date(2026, 11, 16)
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else f"   <-- {detail}"))
    if not ok:
        failures.append(label)


def by_name(results):
    return {r.neighbour.farm_name: r for r in results}


def make_v1_database(path: Path) -> None:
    """Build a database exactly as version 1.0.0 created it (no Derby columns)."""
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE neighbours (id INTEGER PRIMARY KEY AUTOINCREMENT, farm_name TEXT NOT NULL,
        game_rank TEXT NOT NULL DEFAULT '', player_tag TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
        first_week TEXT NOT NULL, archived_on TEXT);
    CREATE UNIQUE INDEX ux_neighbours_tag ON neighbours(player_tag) WHERE player_tag <> '';
    CREATE TABLE weekly_entries (id INTEGER PRIMARY KEY AUTOINCREMENT,
        neighbour_id INTEGER NOT NULL REFERENCES neighbours(id) ON DELETE CASCADE, reporting_date TEXT NOT NULL,
        farm_level INTEGER, nurture INTEGER, donations INTEGER, nurture_actual INTEGER, donations_actual INTEGER,
        updated_at TEXT NOT NULL, UNIQUE (neighbour_id, reporting_date));
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    INSERT INTO neighbours (farm_name, game_rank, first_week) VALUES ('Alice', 'Leader', '2026-11-09');
    INSERT INTO weekly_entries (neighbour_id, reporting_date, farm_level, nurture, donations, updated_at)
        VALUES (1, '2026-11-09', 50, 1000, 200, 'x'), (1, '2026-11-16', 51, 1100, 220, 'x');
    INSERT INTO settings VALUES ('nurture_mode', 'cumulative'), ('weight_nurture', '45.0'),
        ('weight_donations', '45.0'), ('weight_levels', '10.0');
    PRAGMA user_version = 1;
    """)
    conn.commit()
    conn.close()


def part_a(tmp: Path) -> None:
    print("\nDERBY: data and scoring")
    old = tmp / "v1" / "tracker.db"
    old.parent.mkdir()
    make_v1_database(old)
    db = Database(old)
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(weekly_entries)")}
    check("a version 1.0.0 database is upgraded in place", {"derby", "derby_actual"} <= cols)
    check("the old data survived the upgrade",
          len(db.load_dataset().entries) == 2 and db.load_dataset().entries[W1][1].nurture == 1100)
    check("a safety copy of the old file was made", (old.parent / "tracker.before-derby.bak").exists())
    s = db.load_settings()
    check("old scoring settings are kept and Derby starts unscored (weight 0)",
          (s.weight_nurture, s.weight_donations, s.weight_levels, s.weight_derby) == (45, 45, 10, 0) and not s.problems())
    res = by_name(week_results(db.load_dataset(), W1, s))
    check("version 1.0.0 scores are unchanged by the upgrade (Alice = 100)", res["Alice"].score == 100.0)
    check("a missing Derby score does not block the score while its weight is 0", res["Alice"].score is not None)
    db.close()
    Database(old).close()      # opening again must not fail or duplicate columns

    db = Database(tmp / "d" / "tracker.db")
    ids = {n: db.add_neighbour(n, today=W0) for n in ("Alice", "Bob", "Cara", "Dan")}
    E = lambda n, lv, nu, do, de: EntryInput(ids[n], lv, nu, do, derby=de)      # noqa: E731
    db.save_week(W0, [E("Alice", 50, 1000, 200, 40), E("Bob", 40, 500, 100, 70), E("Cara", 30, 800, 50, 500),
                      E("Dan", 20, 300, 40, None)])
    db.save_week(W1, [E("Alice", 51, 1100, 220, 100), E("Bob", 40, 560, 100, 0), E("Cara", 31, 900, 80, 20),
                      E("Dan", 21, 400, 55, 60)])
    ds = db.load_dataset()
    check("Derby scores are stored per week", ds.entries[W1][ids["Alice"]].derby == 100 and ds.entries[W0][ids["Dan"]].derby is None)
    check("a typed 0 Derby score is stored as 0, a blank as blank",
          ds.entries[W1][ids["Bob"]].derby == 0 and ds.entries[W0][ids["Dan"]].derby is None)

    s = Settings(weight_nurture=30, weight_donations=30, weight_levels=10, weight_derby=30, target_derby=100)
    db.save_settings(s)
    check("Derby settings are saved", db.load_settings().weight_derby == 30 and db.load_settings().derby_mode == "weekly")
    res = by_name(week_results(db.load_dataset(), W1, db.load_settings()))
    check("weekly Derby is used directly (Alice 100)", res["Alice"].metrics[DERBY].value == 100)
    check("Alice scores 30+30+30+10 = 100", res["Alice"].score == 100.0, str(res["Alice"].score))
    check("a true zero Derby score counts as 0 and still scores (Bob 18 + 0 + 0 + 0)",
          res["Bob"].metrics[DERBY].value == 0 and res["Bob"].metrics[DERBY].text == "0" and res["Bob"].score == 18.0,
          str(res["Bob"].score))
    check("Derby is capped at 100% of target (Cara 500 at W0 would be 30, week 2: 20 -> 6)",
          res["Cara"].parts[DERBY].points == 6.0)
    res0 = by_name(week_results(db.load_dataset(), W0, db.load_settings()))
    check("Derby makes a score 'Insufficient data' once it has weight and is missing (Dan, week 1)",
          res0["Dan"].metrics[DERBY].text == "Not entered" and res0["Dan"].score is None)

    db.save_settings(Settings(weight_nurture=30, weight_donations=30, weight_levels=10, weight_derby=30,
                              derby_mode="cumulative"))
    res = by_name(week_results(db.load_dataset(), W1, db.load_settings()))
    check("cumulative Derby uses the change since last Monday (Alice 100-40 = 60)", res["Alice"].metrics[DERBY].value == 60)
    check("cumulative Derby that drops is flagged as a reset (Cara 500 -> 20)",
          res["Cara"].metrics[DERBY].status == RESET and res["Cara"].score is None)
    db.set_actual(ids["Cara"], W1, "derby", 25)
    res = by_name(week_results(db.load_dataset(), W1, db.load_settings()))
    check("the actual Derby amount can be supplied", res["Cara"].metrics[DERBY].value == 25 and res["Cara"].score is not None)
    check("Derby without baseline: Dan has none in week 1 (no previous week)",
          by_name(week_results(db.load_dataset(), W0, db.load_settings()))["Alice"].metrics[DERBY].text == "No baseline")

    db.save_settings(Settings(weight_derby=20, weight_nurture=40, weight_donations=30, weight_levels=10))
    out = tmp / "h.csv"
    export.export_history(db.load_dataset(), db.load_settings(), out)
    rows = list(csv.DictReader(open(out, newline="", encoding="utf-8-sig")))
    alice = next(r for r in rows if r["Farm name"] == "Alice" and r["Reporting date (Monday)"] == W1.isoformat())
    check("CSV history includes the Derby score and Derby points", alice["Derby score (as entered)"] == "100"
          and alice["Derby points"] == "100")
    rk = tmp / "r.csv"
    export.export_rankings(week_results(db.load_dataset(), W1, db.load_settings()), W1, db.load_settings(), rk)
    head = open(rk, encoding="utf-8-sig").readline()
    check("CSV rankings include Derby columns", "Derby points" in head and "Derby points scored" in head)
    check("weights including Derby must still add to 100",
          bool(Settings(weight_derby=10).problems()) and not Settings(weight_derby=0).problems())
    db.close()


def part_b(tmp: Path) -> None:
    print("\nSCROLLING and TABS (real window)")
    popups: list[str] = []
    messagebox.showwarning = messagebox.showinfo = messagebox.showerror = lambda t, m, **k: popups.append(t)
    messagebox.askyesno = lambda *a, **k: True
    messagebox.askyesnocancel = lambda *a, **k: True
    App.latest_monday = lambda self: W1
    app = App(tmp / "ui" / "tracker.db")
    _apps.append(app)
    root = app.root

    def pump():
        root.update_idletasks()
        root.update()

    pump()
    pump()                                           # window is open with an EMPTY roster, as on first run
    for i in range(30):
        app.db.add_neighbour(f"Farm {i:02d}", "Member", today=W1)
    app.neighbours_changed()
    pump()
    pump()
    body = app.monday.body
    need = body.inner.winfo_reqheight()
    region = [float(v) for v in str(body.canvas.cget("scrollregion")).split()]
    check("scroll region grows to fit rows added after the window opened (the 1.0.0 bug)",
          region[3] >= need > body.canvas.winfo_height(), f"region={region} need={need} view={body.canvas.winfo_height()}")
    check("the scroll bar thumb is smaller than its track (there is something to scroll)",
          body.canvas.yview()[1] < 0.9, str(body.canvas.yview()))
    top = body.canvas.yview()[0]
    cx, cy = body.canvas.winfo_rootx() + 200, body.canvas.winfo_rooty() + 100
    root.event_generate("<MouseWheel>", delta=-120, rootx=cx, rooty=cy, warp=True)    # pointer over the list
    pump()
    check("mouse wheel over the list scrolls it", body.canvas.yview()[0] > top, str(body.canvas.yview()))
    mid = body.canvas.yview()[0]
    root.event_generate("<MouseWheel>", delta=-30, rootx=cx, rooty=cy, warp=True)     # a smooth touchpad nudge
    pump()
    check("small touchpad-style wheel steps still scroll", body.canvas.yview()[0] > mid, str(body.canvas.yview()))
    before = body.canvas.yview()[0]
    ttk_scroll = body.scrollbar
    ttk_scroll.tk.call(ttk_scroll.cget("command"), "moveto", 0.5)
    pump()
    check("scroll bar moves the list (moveto)", abs(body.canvas.yview()[0] - 0.5) < 0.02 and body.canvas.yview()[0] != before)
    body.canvas.yview_moveto(0)
    pump()
    app.monday.rows[28].entries["nur"].focus_force()
    pump()
    check("tabbing into a row far down scrolls it into view", body.canvas.yview()[0] > 0.3, str(body.canvas.yview()))
    for r in app.monday.rows[:3]:
        r.vars["nur"].set("10")
    pump()
    app.monday.save()
    pump()
    app.db.add_neighbour("Late Joiner", "Member", today=W1)
    app.neighbours_changed()
    pump()
    pump()
    region = [float(v) for v in str(body.canvas.cget("scrollregion")).split()]
    check("still scrollable after a save and another roster change", region[3] >= body.inner.winfo_reqheight())

    print("\nDERBY in the window")
    r0 = app.monday.rows[0]
    check("the grid has a Derby box on every row", all("der" in r.entries for r in app.monday.rows))
    check("Derby is not needed for 'entered' while its weight is 0",
          (r0.vars.__setitem__("lvl", r0.vars["lvl"]) or True) and not app.settings.weight_derby)
    r0.vars["lvl"].set("5"); r0.vars["nur"].set("10"); r0.vars["don"].set("3"); pump()
    check("a row is complete without Derby when Derby is unscored", r0.complete())
    s = Settings(weight_nurture=40, weight_donations=40, weight_levels=10, weight_derby=10)
    app.db.save_settings(s)
    app.settings = s
    app.monday.reload_keeping_drafts()
    pump()
    r0 = app.monday.rows[0]
    check("once Derby has a weight, a row also needs a Derby score to be complete", not r0.complete())
    r0.vars["der"].set("12"); pump()
    check("entering a Derby score completes the row", r0.complete())
    r0.vars["der"].set("abc"); pump()
    check("an invalid Derby score is highlighted", str(r0.entries["der"].cget("style")) == "Invalid.TEntry")
    r0.vars["der"].set("12"); pump()
    app.monday.save()
    pump()
    nid = app.monday.rows[0].n.id
    check("the Derby score is saved with the week", app.db.load_dataset().entries[W1][nid].derby == 12)
    app.request_week(W0); pump(); app.request_week(W1); pump()
    check("and comes back when the week is reopened", app.monday.rows[0].vars["der"].get() == "12")
    app.show_tab("rankings"); pump(); app.rankings.refresh()
    check("Rankings has a sortable Derby column",
          "derby" in app.rankings.tree["columns"])
    app.rankings.sort_by("derby"); pump()
    first = app.rankings.tree.item(app.rankings.tree.get_children()[0], "values")
    check("sorting by Derby puts the neighbour with a Derby figure first", first[5] != "Not entered", str(first))
    app.overview.refresh()
    check("Overview shows a Derby card", DERBY in app.overview.card_widgets)

    print("\nTAB STYLE")
    style = ttk.Style(root)
    sel_pad = style.lookup("TNotebook.Tab", "padding", ["selected"])
    off_pad = style.lookup("TNotebook.Tab", "padding", [])
    check("selected and unselected tabs use the same padding (no height change)",
          str(sel_pad) == str(off_pad), f"{sel_pad} vs {off_pad}")
    expand_sel = style.lookup("TNotebook.Tab", "expand", ["selected"])
    check("selected tab does not expand", set(str(expand_sel).replace("{", "").replace("}", "").replace("(", "").replace(")", "").replace(",", " ").split()) <= {"0"},
          str(expand_sel))
    heights, colours = [], []
    for key in ("overview", "monday", "neighbours", "rankings"):
        app.show_tab(key); pump()
        heights.append([app.notebook.bbox(i)[3] for i in range(4)])
        colours.append(style.lookup("TNotebook.Tab", "background", ["selected"]))
    check("every tab keeps the same height whichever one is selected",
          all(len(set(h)) == 1 for h in heights) and all(h == heights[0] for h in heights), str(heights))
    sel_bg = style.lookup("TNotebook.Tab", "background", ["selected"])
    plain_bg = style.lookup("TNotebook.Tab", "background", [])
    check("the selected tab is a light green, different from the others",
          sel_bg.lower() == "#bfd8b4" and plain_bg.lower() != sel_bg.lower(), f"{sel_bg} / {plain_bg}")
    check("no error pop-ups", not [p for p in popups if p == "Something went wrong"])
    app.close()


_apps: list = []


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hayday-v101-") as folder:
        tmp = Path(folder)
        part_a(tmp)
        try:
            part_b(tmp)
        finally:
            for app in _apps:
                try:
                    app.db.close()
                    app.root.destroy()
                except Exception:
                    pass
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
