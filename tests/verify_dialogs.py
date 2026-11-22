"""Checks the dialogs, CSV export, backup button and the counter-reset flow inside the real window.
Run: py -3 tests\verify_dialogs.py   (uses a temporary database only)."""
import sys, tempfile, os, csv, sqlite3
from pathlib import Path
from datetime import date
from tkinter import messagebox, filedialog
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hayday_tracker.app import App
from hayday_tracker import ui_dialogs
from hayday_tracker.models import Settings, EntryInput
sys.stdout.reconfigure(encoding="utf-8")
W0, W1 = date(2026, 11, 9), date(2026, 11, 16)
App.latest_monday = lambda self: W1
tmp = Path(tempfile.mkdtemp())
msgs = []
messagebox.showinfo = lambda t, m, **k: msgs.append((t, m))
messagebox.showwarning = lambda t, m, **k: msgs.append((t, m))
messagebox.showerror = lambda t, m, **k: msgs.append((t, m))
messagebox.askyesno = lambda *a, **k: True
app = App(tmp / "t.db"); root = app.root; root.update()
ok = True
def check(label, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + label)

# bulk add through the real dialog class (bypass modal loop)
orig_show = ui_dialogs.BulkAddDialog.show
def fake_bulk(self):
    self.text.insert("1.0", "Sunny Acres, Elder\nBarn Again\n\nSunny Acres\n=Evil, Member\n"); self._ok(); return self.result
ui_dialogs.BulkAddDialog.show = fake_bulk
app.show_tab("neighbours"); app.neighbours.add_several(); root.update()
names = sorted(n.farm_name for n in app.db.list_neighbours())
check("bulk add: 3 added, duplicate skipped", names == ["=Evil", "Barn Again", "Sunny Acres"])
check("bulk add: rank parsed", next(n for n in app.db.list_neighbours() if n.farm_name == "Sunny Acres").game_rank == "Elder")
check("bulk add: new neighbours appear in Monday grid", len(app.monday.rows) == 3)

# Settings dialog
d = ui_dialogs.SettingsDialog(root, Settings())
d.weight_vars["nurture"].set("50"); d._save()
check("settings dialog rejects weights != 100", d.result is None and "100" in d.error.cget("text"))
d.weight_vars["nurture"].set("30"); d.weight_vars["donations"].set("50"); d.weight_vars["levels"].set("20")
d.target_vars["nurture"].set("250"); d.mode_vars["nurture"].set(ui_dialogs.MODE_LABELS["weekly"]); d._save()
res = d.result
check("settings dialog returns new settings", res and res.weight_nurture == 30 and res.target_nurture == 250 and res.nurture_mode == "weekly")
d2 = ui_dialogs.SettingsDialog(root, Settings()); d2.target_vars["levels"].set("0"); d2._save()
check("settings dialog rejects zero target", d2.result is None and d2.error.cget("text"))
ui_dialogs.SettingsDialog.show = lambda self: res
app.edit_settings(); root.update()
check("settings persisted and reloaded", app.db.load_settings().weight_nurture == 30 and app.settings.nurture_mode == "weekly")
check("grid header reflects weekly nurture", "earned this week" in " ".join(w.cget("text") for w in app.monday.frame_header.winfo_children() if w.winfo_class() == "Label"))
ui_dialogs.SettingsDialog.show = lambda self: Settings()
app.edit_settings()

# Actual-amount dialog
a = ui_dialogs.ActualAmountDialog(root, "Sunny", "nurture", 800, 200, None)
a.var.set("-5"); a._ok(); check("actual dialog rejects negatives", a.result is None and a.error.cget("text"))
a.var.set("1,250"); a._ok(); check("actual dialog accepts 1,250", a.result == (1250,))
b = ui_dialogs.ActualAmountDialog(root, "Sunny", "nurture", 800, 200, 40); b.var.set(""); b._ok()
check("actual dialog can clear (blank -> (None,))", b.result == (None,))

# Monday grid: reset flagged, click-to-set path
ids = {n.farm_name: n.id for n in app.db.list_neighbours()}
app.db.save_week(W0, [EntryInput(ids["Sunny Acres"], 50, 800, 100)]); app.request_week(W0); app.request_week(W1); root.update()
row = {r.n.farm_name: r for r in app.monday.rows}["Sunny Acres"]
for k, v in (("nur", "200"), ("don", "120"), ("lvl", "51")): row.vars[k].set(v)
root.update()
ui_dialogs.ActualAmountDialog.show = lambda self: (self.var.set("75"), self._ok(), self.result)[-1]
row.fix_drops(); root.update()
check("clicking the flag stores a pending actual (75)", row.actual["nurture"] == 75 and "Actual earned: 75" in row.status.cget("text"))
app.monday.save(); root.update()
check("actual amount saved with the week", app.db.load_dataset().entries[W1][ids["Sunny Acres"]].nurture_actual == 75)
row = {r.n.farm_name: r for r in app.monday.rows}["Sunny Acres"]
check("actual amount reloads in the grid", row.actual["nurture"] == 75)
row.vars["nur"].set("900"); root.update()
check("fixing the typo removes the stale actual", row.to_input().nurture_actual is None)

# Export & backup via the app (file dialogs patched)
out = tmp / "hist.csv"
filedialog.asksaveasfilename = lambda **k: str(out)
app.export_history(); check("export history writes a CSV", out.exists() and len(list(csv.reader(open(out, encoding="utf-8-sig")))) >= 2)
out2 = tmp / "rank.csv"; filedialog.asksaveasfilename = lambda **k: str(out2)
app.export_rankings(); check("export rankings writes a CSV", out2.exists())
out3 = tmp / "bk.sqlite"; filedialog.asksaveasfilename = lambda **k: str(out3)
app.backup(); check("backup button writes a valid SQLite file", sqlite3.connect(out3).execute("PRAGMA integrity_check").fetchone()[0] == "ok")
filedialog.asksaveasfilename = lambda **k: str(app.db.path)
msgs.clear(); app.backup(); check("backup refuses to overwrite the live database", any("Backup failed" in m[0] for m in msgs))

# Delete confirmation text
msgs.clear()
shown = []
messagebox.askyesno = lambda t, m, **k: (shown.append(m), False)[1]
app.show_tab("neighbours"); app.neighbours.tree.selection_set(str(ids["Sunny Acres"])); root.update()
app.neighbours.delete()
check("delete confirmation shows the record count", shown and "2 weekly entries" in shown[0])
check("declining the delete keeps the neighbour", app.db.get_neighbour(ids["Sunny Acres"]) is not None)
check("no unhandled errors", not [m for m in msgs if m[0] == "Something went wrong"])
app.db.close(); root.destroy()
print("ALL OK" if ok else "SOME FAILED")
