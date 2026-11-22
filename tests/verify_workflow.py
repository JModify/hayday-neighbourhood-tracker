"""End-to-end check of the tracker's workflow against a temporary database.

Run it with:   python tests\\verify_workflow.py

Part A exercises the database and scoring rules directly.
Part B opens the real Tkinter window and drives the Monday Update grid, the
Neighbours tab and the Rankings tab the way you would.

It never touches %LOCALAPPDATA%\\HayDayTracker: everything lives in a temp folder
that is deleted at the end.
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tkinter import messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hayday_tracker import export                                   # noqa: E402
from hayday_tracker.db import Database, ValidationError             # noqa: E402
from hayday_tracker.models import EntryInput, Settings              # noqa: E402
from hayday_tracker.scoring import (DONATIONS, LEVELS, NURTURE,      # noqa: E402
                                    NO_BASELINE, OK, OVERRIDE, RESET, week_results)
from hayday_tracker.util import BRISBANE, most_recent_monday, parse_count  # noqa: E402

W0, W1, W2 = date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
failures: list[str] = []
_apps: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("  PASS  " if condition else "  FAIL  ") + label + ("" if condition else f"   <-- {detail}"))
    if not condition:
        failures.append(label)


def by_name(results):
    return {r.neighbour.farm_name: r for r in results}


# =====================================================================================
def part_a(tmp: Path) -> None:
    print("\nPART A: database and scoring rules")
    db_path = tmp / "a" / "tracker.db"
    db = Database(db_path)
    check("fresh database is empty", not db.list_neighbours() and db.entry_dates() == [])

    print(" dates (Australia/Brisbane)")
    check("Sunday 22 Nov 2026 -> Monday 16 Nov", most_recent_monday(date(2026, 11, 22)) == W1)
    check("a Monday is its own reporting date", most_recent_monday(W2) == W2)
    late_sunday_utc = datetime(2026, 11, 22, 20, 0, tzinfo=timezone.utc)
    brisbane_day = late_sunday_utc.astimezone(BRISBANE).date()
    check("Sunday 8pm UTC is already Monday in Brisbane",
          brisbane_day == W2 and most_recent_monday(brisbane_day) == W2, str(brisbane_day))
    check("blank is not zero", parse_count("") == (None, None) and parse_count("0") == (0, None))
    check("bad numbers rejected", parse_count("-3")[1] and parse_count("abc")[1] and parse_count("1.5")[1])

    ids = {n: db.add_neighbour(n, r, today=W0) for n, r in
           [("Alice", "Leader"), ("Bob", "Elder"), ("Cara", "Member"), ("Dan", "Member"),
            ("Eve", "Member"), ("Frank", "Member")]}
    S = lambda n, lv, nu, do: EntryInput(ids[n], lv, nu, do)           # noqa: E731
    db.save_week(W0, [S("Alice", 50, 1000, 200), S("Bob", 40, 500, 100), S("Cara", 30, 800, 50),
                      S("Dan", 20, 300, 40), S("Frank", 50, 1000, 200)])          # Eve has no W0 data
    db.save_week(W1, [S("Alice", 51, 1100, 220), S("Bob", 40, 560, 100), S("Cara", 31, 200, 80),
                      S("Dan", 21, 400, 55), S("Eve", 10, 100, 10), S("Frank", 51, 1100, 220)])

    print(" scoring: true zero, missing baseline, reset counter")
    ds = db.load_dataset()
    res = by_name(week_results(ds, W1, db.load_settings()))
    check("Alice scores 100 (all targets met)", res["Alice"].score == 100.0, str(res["Alice"].score))
    bob = res["Bob"]
    check("Bob's true zero levels is 0 and counts (status ok)",
          bob.metrics[LEVELS].value == 0 and bob.metrics[LEVELS].status == OK and bob.metrics[LEVELS].text == "0")
    check("Bob's true zero donations is 0", bob.metrics[DONATIONS].value == 0 and bob.metrics[DONATIONS].text == "0")
    check("Bob scores 27.00 = 45 x 60%", bob.score == 27.0, str(bob.score))
    dan = res["Dan"]
    check("Dan = 45 + 45 x 75% + 10 = 88.75", dan.score == 88.75, str(dan.score))
    eve = res["Eve"]
    check("Eve has no baseline for every metric",
          all(eve.metrics[k].status == NO_BASELINE for k in (LEVELS, NURTURE, DONATIONS)))
    check("Eve shows Insufficient data and no position", eve.score is None and eve.position is None)
    check("Eve's cells read 'No baseline'", eve.metrics[NURTURE].text == "No baseline")
    cara = res["Cara"]
    check("Cara's nurture drop (800 -> 200) is flagged as a reset",
          cara.metrics[NURTURE].status == RESET and cara.metrics[NURTURE].value is None)
    check("Cara has Insufficient data while reset is unresolved", cara.score is None)
    check("Cara's donations still count (80-50=30)", cara.metrics[DONATIONS].value == 30)
    check("tied scores share a position (Alice & Frank = 1, Dan = 3, Bob = 4)",
          (res["Alice"].position, res["Frank"].position, dan.position, bob.position) == (1, 1, 3, 4),
          str([(r.neighbour.farm_name, r.position) for r in res.values()]))

    db.set_actual(ids["Cara"], W1, "nurture", 50)
    res = by_name(week_results(db.load_dataset(), W1, db.load_settings()))
    cara = res["Cara"]
    check("supplying the actual amount resolves the reset (status override, 50)",
          cara.metrics[NURTURE].status == OVERRIDE and cara.metrics[NURTURE].value == 50)
    check("Cara now scores 22.5 + 45 + 10 = 77.50", cara.score == 77.5, str(cara.score))
    check("Cara ranks 4th, Bob 5th", (cara.position, res["Bob"].position) == (4, 5))
    res0 = by_name(week_results(db.load_dataset(), W0, db.load_settings()))
    check("first week has no baseline anywhere (all Insufficient data)",
          all(r.score is None for r in res0.values() if r.entry))
    check("position change is relative to last week (none ranked before -> None)",
          res["Alice"].position_change is None)

    print(" settings")
    s = db.load_settings()
    check("defaults 45/45/10 and targets 100/20/1",
          (s.weight_nurture, s.weight_donations, s.weight_levels) == (45, 45, 10)
          and (s.target_nurture, s.target_donations, s.target_levels) == (100, 20, 1))
    weekly = Settings(nurture_mode="weekly", donations_mode="weekly")
    db.save_settings(weekly)
    wk = by_name(week_results(db.load_dataset(), W1, db.load_settings()))
    check("weekly mode uses values directly (Alice nurture 1,100)", wk["Alice"].metrics[NURTURE].value == 1100)
    check("weekly mode has no reset concept (Cara nurture 200)", wk["Cara"].metrics[NURTURE].value == 200)
    try:
        db.save_settings(Settings(weight_nurture=50))
        check("weights that do not add to 100 are rejected", False)
    except ValidationError:
        check("weights that do not add to 100 are rejected", True)
    db.save_settings(Settings())

    print(" weekly entries")
    n_before = db.conn.execute("SELECT COUNT(*) FROM weekly_entries").fetchone()[0]
    db.save_week(W1, [S("Alice", 52, 1150, 230)])
    n_after = db.conn.execute("SELECT COUNT(*) FROM weekly_entries").fetchone()[0]
    check("re-saving updates the existing record (one entry per neighbour per date)", n_before == n_after)
    ds = db.load_dataset()
    check("the update took effect", ds.entries[W1][ids["Alice"]].farm_level == 52)
    try:
        db.save_week(W1, [S("Alice", 99, 1, 1), EntryInput(99999, 1, 1, 1)])    # second row is invalid
    except Exception:
        pass
    check("a failed save rolls back everything (one transaction)",
          db.load_dataset().entries[W1][ids["Alice"]].farm_level == 52)
    try:
        db.save_week(date(2026, 11, 17), [S("Alice", 1, 1, 1)])
        check("non-Monday reporting date rejected", False)
    except ValidationError:
        check("non-Monday reporting date rejected", True)
    db.save_week(W1, [S("Alice", 51, 1100, 220)])

    print(" rename, archive, delete")
    db.update_neighbour(ids["Bob"], "Robert", "Elder", "#BOB123", "likes pigs")
    ds = db.load_dataset()
    check("rename keeps the same internal ID and history",
          ds.neighbours[ids["Bob"]].farm_name == "Robert" and ids["Bob"] in ds.entries[W0] and ids["Bob"] in ds.entries[W1])
    check("a duplicate player tag is refused", _raises(lambda: db.update_neighbour(ids["Dan"], "Dan", "", "#bob123", "")))
    db.archive_neighbour(ids["Dan"], today=W2)
    check("archived neighbour is hidden from the active list",
          ids["Dan"] not in {n.id for n in db.list_neighbours(include_archived=False)})
    res = by_name(week_results(db.load_dataset(), W1, db.load_settings()))
    check("archived neighbour keeps their W1 result", "Dan" in res and res["Dan"].score == 88.75)
    res2 = by_name(week_results(db.load_dataset(), W2, db.load_settings()))
    check("archived neighbour is not expected in the new week", "Dan" not in res2)
    db.restore_neighbour(ids["Dan"])
    check("restore brings them back", ids["Dan"] in {n.id for n in db.list_neighbours(include_archived=False)})
    count, first, last = db.entry_count(ids["Frank"])
    check("delete summary counts the records", (count, first, last) == (2, W0, W1))
    check("permanent delete removes the neighbour and their entries",
          db.delete_neighbour(ids["Frank"]) == 2
          and db.get_neighbour(ids["Frank"]) is None
          and db.conn.execute("SELECT COUNT(*) FROM weekly_entries WHERE neighbour_id=?", (ids["Frank"],)).fetchone()[0] == 0)

    print(" CSV export and backup")
    ds, st = db.load_dataset(), db.load_settings()
    hist = tmp / "history.csv"
    rows = export.export_history(ds, st, hist)
    with open(hist, newline="", encoding="utf-8-sig") as fh:
        table = list(csv.DictReader(fh))
    check("history CSV has one row per saved entry", rows == len(table) == db.conn.execute(
        "SELECT COUNT(*) FROM weekly_entries").fetchone()[0])
    robert = next(r for r in table if r["Farm name"] == "Robert" and r["Reporting date (Monday)"] == W1.isoformat())
    check("CSV keeps the true zero as 0 (not blank)", robert["Levels gained"] == "0" and robert["Donations made"] == "0")
    eve_row = next(r for r in table if r["Farm name"] == "Eve")
    check("CSV leaves missing baselines blank with a note",
          eve_row["Levels gained"] == "" and "no baseline" in eve_row["Data notes"])
    cara_row = next(r for r in table if r["Farm name"] == "Cara" and r["Reporting date (Monday)"] == W1.isoformat())
    check("CSV shows the supplied actual amount", cara_row["Nurture points"] == "50")
    db.add_neighbour("=HYPERLINK(\"x\")", today=W0)
    export.export_history(db.load_dataset(), st, hist)
    rk = tmp / "rank.csv"
    export.export_rankings(week_results(db.load_dataset(), W1, st), W1, st, rk)
    text = rk.read_text(encoding="utf-8-sig")
    check("rankings CSV neutralises formula-looking names", "'=HYPERLINK" in text and ",=HYPERLINK" not in text)

    backup = tmp / "backup" / "tracker-backup.sqlite"
    db.backup_to(backup)
    restored = Database(backup)
    check("backup file opens and holds the same data",
          restored.load_dataset().entries == db.load_dataset().entries
          and {n.farm_name for n in restored.list_neighbours()} == {n.farm_name for n in db.list_neighbours()})
    check("backup passes SQLite's integrity check",
          sqlite3.connect(backup).execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    restored.close()
    db.close()
    db2 = Database(db_path)
    check("data reloads identically after reopening the file", len(db2.list_neighbours()) == 6)
    db2.close()


def _raises(fn) -> bool:
    try:
        fn()
    except ValidationError:
        return True
    return False


# =====================================================================================
def part_b(tmp: Path) -> None:
    print("\nPART B: the real window (Monday Update, Neighbours, Rankings)")
    from hayday_tracker.app import App

    popups: list[tuple[str, str]] = []
    messagebox.showwarning = lambda title, msg, **kw: popups.append((title, msg))
    messagebox.showinfo = lambda title, msg, **kw: popups.append((title, msg))
    messagebox.showerror = lambda title, msg, **kw: popups.append((title, msg))
    messagebox.askyesno = lambda *a, **kw: True
    messagebox.askyesnocancel = lambda *a, **kw: True
    App.latest_monday = lambda self: W1            # pretend "today" is the week of Monday 16 Nov 2026

    app = App(tmp / "b" / "tracker.db")
    _apps.append(app)
    root = app.root

    def pump():
        root.update_idletasks()
        root.update()

    pump()
    check("opens on the Monday Update tab", app.notebook.tab(app.notebook.select(), "text") == "Monday Update")
    check("shows the empty-state prompt with no neighbours", app.monday.rows == [])
    check("real database starts empty (no neighbours, no entries)",
          app.db.list_neighbours() == [] and app.db.entry_dates() == [])

    for name, rank in [("Alice", "Leader"), ("Bob", "Elder"), ("Cara", "Member"), ("Dan", "Member")]:
        app.db.add_neighbour(name, rank, today=W0)
    app.neighbours_changed()
    pump()

    def rows():
        return {r.n.farm_name: r for r in app.monday.rows}

    def fill(row, lvl=None, nur=None, don=None):
        for key, val in (("lvl", lvl), ("nur", nur), ("don", don)):
            if val is not None:
                row.vars[key].set(str(val))
        pump()

    print(" week 1 (Monday 9 Nov): enter the roster")
    app.request_week(W0)
    pump()
    r = rows()
    check("every active neighbour has a row", set(r) == {"Alice", "Bob", "Cara", "Dan"})
    check("rows follow rank order (Leader, Elder, Members)", [x.n.farm_name for x in app.monday.rows][:2] == ["Alice", "Bob"])
    check("nothing prefilled in nurture/donations; level blank with no history",
          all(x.vars["nur"].get() == "" and x.vars["don"].get() == "" and x.vars["lvl"].get() == "" for x in r.values()))
    first = app.monday.rows[0]
    order = []
    w = first.entries["lvl"]
    for _ in range(4):
        order.append(w)
        w = w.tk_focusNext()
    check("Tab order runs level -> nurture -> donations -> next row",
          order[1] is first.entries["nur"] and order[2] is first.entries["don"]
          and order[3] is app.monday.rows[1].entries["lvl"])
    first.entries["nur"].focus_force()
    pump()
    first._move("nur", +1)
    pump()
    check("Enter / arrow keys move down a row", root.focus_get() is app.monday.rows[1].entries["nur"])
    for name, lv, nu, do in [("Alice", 50, "1,000", 200), ("Bob", 40, 500, 100), ("Cara", 30, 800, 50), ("Dan", 20, 300, 0)]:
        fill(r[name], lv, nu, do)
    check("progress reads 4 of 4", app.monday.progress_label.cget("text").startswith("4 of 4 neighbours entered"))
    app.monday.save()
    pump()
    check("week 1 saved", len(app.db.load_dataset().entries[W0]) == 4)
    check("comma-formatted numbers are stored as plain integers", app.db.load_dataset().entries[W0][
        next(n.id for n in app.db.list_neighbours() if n.farm_name == "Alice")].nurture == 1000)

    print(" week 2 (Monday 16 Nov): partial save, reopen")
    app.request_week(W1)
    pump()
    r = rows()
    check("farm level prefilled from last week", r["Alice"].vars["lvl"].get() == "50" and r["Dan"].vars["lvl"].get() == "20")
    check("nurture and donations left blank", all(x.vars["nur"].get() == "" for x in r.values()))
    check("last week's numbers are shown beside the entry boxes",
          any(w.cget("text") == "1,000" for w in app.monday.body.inner.winfo_children() if w.winfo_class() == "TLabel"))
    check("progress starts at 0 of 4", app.monday.progress_label.cget("text").startswith("0 of 4"))
    fill(r["Alice"], 51, 1100, 220)
    fill(r["Bob"], 40, 560, 100)                    # same donation total as last week: a genuine zero earned
    fill(r["Cara"], 31, 200, 80)                    # nurture total went DOWN: counter reset
    fill(r["Dan"], None, 400)                       # donations still blank
    check("a drop in a cumulative counter is flagged in the grid",
          "dropped" in r["Cara"].status.cget("text") and str(r["Cara"].entries["nur"].cget("style")) == "Warn.TEntry")
    check("progress shows 3 of 4 with one partly entered",
          app.monday.progress_label.cget("text").startswith("3 of 4 neighbours entered")
          and "1 partly entered" in app.monday.progress_label.cget("text"))
    r["Bob"].vars["don"].set("abc")
    pump()
    check("invalid text is highlighted beside the field",
          str(r["Bob"].entries["don"].cget("style")) == "Invalid.TEntry" and "✗" in r["Bob"].status.cget("text"))
    saved_before = len(app.db.load_dataset().entries.get(W1, {}))
    app.monday.save()
    pump()
    check("saving is blocked while a field is invalid", len(app.db.load_dataset().entries.get(W1, {})) == saved_before
          and any("Check the highlighted" in p[0] for p in popups))
    r["Bob"].vars["don"].set("100")
    pump()
    app.monday.save()
    pump()
    ds = app.db.load_dataset()
    ids = {n.farm_name: n.id for n in app.db.list_neighbours()}
    check("partial update saved (Dan keeps blank donations, not 0)",
          ds.entries[W1][ids["Dan"]].donations is None and ds.entries[W1][ids["Dan"]].nurture == 400)
    check("a typed 0 is stored as 0, not blank (Dan, week 1)", ds.entries[W0][ids["Dan"]].donations == 0)
    check("a blank is stored as blank, not 0 (Dan, week 2)", ds.entries[W1][ids["Dan"]].donations is None)
    app.request_week(W0)
    pump()
    app.request_week(W1)
    pump()
    r = rows()
    check("reopening the week restores saved entries",
          r["Alice"].vars["nur"].get() == "1100" and r["Bob"].vars["don"].get() == "100" and r["Dan"].vars["don"].get() == "")
    check("progress after reopening: 3 of 4", app.monday.progress_label.cget("text").startswith("3 of 4"))
    fill(r["Dan"], None, None, 55)
    app.monday.save()
    pump()
    check("finishing the week later completes it (4 of 4)", app.monday.progress_label.cget("text").startswith("4 of 4"))

    print(" Rankings tab")
    app.show_tab("rankings")
    pump()
    app.rankings.refresh()
    tree = app.rankings.tree
    vals = {tree.item(i, "values")[1]: tree.item(i, "values") for i in tree.get_children()}
    # columns: pos, name, levels, nurture, donations, score, change, notes
    check("Alice scores 100.00 in position 1", vals["Alice"][0] == "1" and vals["Alice"][5] == "100.00", str(vals["Alice"]))
    check("a true zero (nothing earned) shows as 0 and still scores", vals["Bob"][2] == "0" and vals["Bob"][4] == "0" and vals["Bob"][5] == "27.00",
          str(vals["Bob"]))
    check("reset counter is labelled and gives Insufficient data",
          "Counter reset" in vals["Cara"][3] and vals["Cara"][5] == "Insufficient data", str(vals["Cara"]))
    app.monday.load_week(W0)    # W0 has no earlier week at all
    app.request_week(W0)
    pump()
    app.rankings.refresh()
    vals0 = {tree.item(i, "values")[1]: tree.item(i, "values") for i in tree.get_children()}
    check("missing baseline is labelled 'No baseline' and gives Insufficient data",
          vals0["Alice"][3] == "No baseline" and vals0["Alice"][5] == "Insufficient data", str(vals0["Alice"]))
    app.request_week(W1)
    pump()
    app.rankings.refresh()
    app.rankings.sort_by("nurture")
    pump()
    order = [tree.item(i, "values")[1] for i in tree.get_children()]
    check("sort by Nurture (highest first, missing last)", order == ["Alice", "Dan", "Bob", "Cara"], str(order))
    app.rankings.sort_by("nurture")
    pump()
    order = [tree.item(i, "values")[1] for i in tree.get_children()]
    check("clicking again reverses it (missing still last)", order == ["Bob", "Alice", "Dan", "Cara"], str(order))
    app.rankings.sort_by("name")
    pump()
    check("sort by name works", [tree.item(i, "values")[1] for i in tree.get_children()] == ["Alice", "Bob", "Cara", "Dan"])
    tree.selection_set(str(ids["Cara"]))
    pump()
    check("breakdown explains the missing metric and offers the actual-amount button",
          "Insufficient data" in app.rankings.bd_note.cget("text") and app.rankings.actual_button.winfo_manager() == "pack")
    app.db.set_actual(ids["Cara"], W1, "nurture", 50)
    app.data_changed(source=app.rankings)
    pump()
    vals = {tree.item(i, "values")[1]: tree.item(i, "values") for i in tree.get_children()}
    check("supplying the actual amount flags it with * and scores Cara",
          vals["Cara"][3] == "50*" and vals["Cara"][5] == "77.50", str(vals["Cara"]))

    print(" Overview tab")
    app.overview.refresh()
    big, delta, partial = app.overview.card_widgets["coverage"]
    check("Overview coverage shows 4 / 4", big.cget("text") == "4 / 4")
    big_n, delta_n, partial_n = app.overview.card_widgets[NURTURE]
    check("Overview nurture total = 100+60+50+100 = 310", big_n.cget("text") == "310", big_n.cget("text"))

    print(" correct a past entry")
    app.request_week(W0)
    pump()
    r = rows()
    r["Alice"].vars["nur"].set("900")
    pump()
    check("edited row is marked unsaved", "unsaved" in app.monday.state_label.cget("text"))
    app.monday.save()
    pump()
    check("past entry corrected in the database", app.db.load_dataset().entries[W0][ids["Alice"]].nurture == 900)
    check("still only one entry per neighbour for that date",
          app.db.conn.execute("SELECT COUNT(*) FROM weekly_entries WHERE reporting_date=?", (W0.isoformat(),)).fetchone()[0] == 4)
    res = by_name(week_results(app.db.load_dataset(), W1, app.settings))
    check("the correction flows through to the next week's results (Alice nurture 200)",
          res["Alice"].metrics[NURTURE].value == 200)
    app.request_week(W1)
    pump()
    app.db.save_week(W1, [EntryInput(ids["Alice"], 51, 1100, 220)])   # put the demo data back

    print(" rename a neighbour without losing history")
    app.show_tab("neighbours")
    pump()
    app.neighbours.tree.selection_set(str(ids["Bob"]))
    pump()
    app.neighbours.name_var.set("Robert's Farm")
    app.neighbours.rank_var.set("Leader")
    app.neighbours.save()
    pump()
    check("same ID, new name and rank", app.db.get_neighbour(ids["Bob"]).farm_name == "Robert's Farm"
          and app.db.get_neighbour(ids["Bob"]).game_rank == "Leader")
    hist = app.neighbours.history.get_children()
    check("detail view still lists both weeks of history", len(hist) == 2, str(hist))
    check("detail view shows latest stats with changes", len(app.neighbours.stats.get_children()) == 4)
    app.request_week(W1)
    pump()
    check("Monday Update shows the new name with the saved numbers",
          "Robert's Farm" in rows() and rows()["Robert's Farm"].vars["nur"].get() == "560")

    print(" archive a neighbour without losing results")
    app.show_tab("neighbours")
    app.neighbours.tree.selection_set(str(ids["Dan"]))
    pump()
    app.neighbours.toggle_archive()
    pump()
    check("archived flag set", app.db.get_neighbour(ids["Dan"]).archived)
    check("Dan no longer appears in the neighbour list by default", not app.neighbours.tree.exists(str(ids["Dan"])))
    app.neighbours.show_archived.set(True)
    app.neighbours.refresh_list()
    check("Dan appears when 'Show archived' is ticked", app.neighbours.tree.exists(str(ids["Dan"])))
    app.request_week(W2)    # a brand-new week is not offered when it is later than 'today'... but can be viewed
    pump()
    check("archived neighbour is absent from a new weekly update", "Dan" not in rows())
    app.request_week(W1)
    pump()
    check("archived neighbour is still shown, with saved numbers, when reopening a past week",
          "Dan" in rows() and rows()["Dan"].vars["nur"].get() == "400" and "archived" in rows()["Dan"].status.master.grid_slaves(
              row=rows()["Dan"].index, column=0)[0].cget("text"))
    app.rankings.refresh()
    names = [app.rankings.tree.item(i, "values")[1] for i in app.rankings.tree.get_children()]
    check("archived neighbour keeps their past result in Rankings", "Dan (archived)" in names, str(names))
    summary = app.neighbours
    check("delete confirmation can state the record count", app.db.entry_count(ids["Dan"])[0] == 2)

    print(" unsaved changes and closing")
    app.request_week(W1)
    pump()
    rows()["Alice"].vars["nur"].set("1234")
    pump()
    check("unsaved typing is detected", app.monday.has_unsaved())
    app.neighbours_changed()
    pump()
    check("typed-but-unsaved numbers survive a roster refresh", rows()["Alice"].vars["nur"].get() == "1234")
    app.monday.discard()
    pump()
    check("discard restores the saved value", rows()["Alice"].vars["nur"].get() == "1100")
    check("no unexpected error pop-ups during the run", not [p for p in popups if p[0] == "Something went wrong"],
          str(popups[-3:]))
    app.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hayday-verify-") as folder:
        tmp = Path(folder)
        local = os.environ.get("LOCALAPPDATA", "")
        assert not str(tmp).startswith(os.path.join(local, "HayDayTracker")), "refusing to touch real data"
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
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
