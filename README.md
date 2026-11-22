# Hay Day Neighbourhood Tracker

**Version 1.0.1**

A small, offline Windows desktop app for your Monday routine: enter each neighbour's farm level, Neighbourhood
Nurture score, total donations and Derby score, then see how everyone (and the neighbourhood as a whole) is progressing.

Python 3.9 or newer (built and tested on 3.12), standard library only (Tkinter + SQLite). No installs, no internet.

## Start it

Double-click **`HayDayTracker.bat`**. The app opens in its own window on the **Monday Update** tab.

If nothing appears, double-click **`HayDayTracker (show errors).bat`** instead; it keeps a console open so you
can read the message. Or run it by hand from this folder:

```powershell
py -3 -m hayday_tracker
```

Python needs the "tcl/tk and IDLE" option ticked (it is by default) when installed from python.org.

## First run

1. Open **Neighbours**, press **Add several…** and paste your roster, one per line (`Sunny Acres, Elder`
   adds a rank too).
2. Go to **Monday Update**. It defaults to the most recent Monday in Brisbane time (the Monday is the reporting
   date for the week that ended the Sunday before).
3. Tab through the grid (farm level, Nurture, donations, Derby) and press **Save update**. You can save part-way and finish later.

The database starts empty. Nothing is pre-loaded.

## The four tabs

| Tab | What it is for |
| --- | --- |
| **Overview** | Selected week's coverage, levels gained, Nurture points, donations and Derby points, with change from the previous week. Totals marked *Partial* only cover part of the roster. |
| **Monday Update** | One row per neighbour: last week's numbers beside this week's boxes. Tab / Enter / arrow keys to move. Progress ("18 of 24 neighbours entered"), red highlights for bad values, amber for a counter that dropped. |
| **Neighbours** | Search, add, edit (farm name, in-game rank, player tag, notes), archive / restore, permanent delete (shows how many records go), plus each neighbour's latest stats and dated history. |
| **Rankings** | Weekly levels gained, Nurture, donations, overall score and leaderboard position change. Click any heading to sort. Select a row to see the full score breakdown. |

Use the week picker (‹ › or the drop-down, ✓ = has data) to open an earlier Monday and enter or correct data.

## How numbers are worked out

* **Blank is not zero.** An empty box means "not entered yet"; type `0` for a true zero.
* **Farm level**: this Monday's level minus the previous Monday's.
* **Nurture, donations and Derby** are each set to either:
  * *Weekly*: the number you enter is what was earned that week, used directly; or
  * *Cumulative*: the number is a running total, so the week's figure is the difference from the
    previous Monday's entry.
  Nurture and donations default to *cumulative*; Derby defaults to *weekly* (a Derby score is normally earned fresh each
  week). Change any of them under **Rankings → Edit settings…**.
* **Missing baseline**: a difference needs an entry for exactly the previous Monday. Without one the cell reads
  *No baseline*, never a guess.
* **Counter reset**: if a cumulative total goes *down*, it is flagged. Click the amber status in Monday Update (or
  double-click the row in Rankings) to enter the amount actually earned that week. The figure then shows with a `*`.
  Until you do, that metric is missing.
* **Overall score** (out of 100) = for each metric, `min(weekly result ÷ target, 100%) × weight`, added up.
  Defaults: weights 45% Nurture, 45% donations, 10% levels, **0% Derby**; weekly targets 100 Nurture, 20 donations,
  1 level, 100 Derby. Weights must add up to 100%. Scores are rounded to 2 decimal places before ranking, so what you see is what is ranked.
  Any metric with a weight above zero is required: if one is missing the score reads *Insufficient data*.
* **Derby scores** are recorded every week, but at the default 0% weight they are not part of the score, so your existing
  rankings do not change. To score them, open **Rankings → Edit settings…**, give Derby a weight (for example 30%), lower the
  others so the total is 100%, and set a weekly target that suits your neighbourhood (100 is only a placeholder). Once Derby
  has a weight it is required like the other metrics: a neighbour with no Derby score for the week shows *Insufficient data*,
  and a Monday Update row only counts as entered when its Derby box is filled in.
* **Leaderboard position**: highest score is 1. Tied scores share a position (1, 1, 3…). The *in-game rank*
  (Leader / Elder / Member, or a number you choose) is separate and is just a label you maintain.
* Changing settings recalculates every week, including past ones. Nothing calculated is stored; only your entries are.

## Your data

Everything is in one SQLite file:

```
%LOCALAPPDATA%\HayDayTracker\hayday_tracker.db
```

That is `C:\Users\<you>\AppData\Local\HayDayTracker`, the same wherever you start the app from.
The **Open data folder** button at the bottom of the window takes you there. A neighbour keeps one internal ID, so renaming them
or changing their rank never loses their history. Archived neighbours disappear from new weekly updates but stay in
past weeks, Rankings and exports.

### Export

**Export CSV** (top right) offers *all weekly entries and results* or *the selected week's rankings*. Files open in Excel.

### Back up

Press **Back up database…** and choose where to save. This writes a complete, consistent copy
(`HayDayTracker-backup-YYYYMMDD-HHMM.sqlite`) even while the app is open. Save it somewhere safe such as OneDrive or a USB stick.

### Restore a backup

1. Close the tracker.
2. Keep the current file in case you change your mind: rename
   `%LOCALAPPDATA%\HayDayTracker\hayday_tracker.db` to `hayday_tracker.old.db`.
3. Copy your backup into that folder and name it exactly `hayday_tracker.db`.
4. Start the tracker. Your data is back.

In PowerShell (adjust the backup path):

```powershell
$dir = "$env:LOCALAPPDATA\HayDayTracker"
Rename-Item "$dir\hayday_tracker.db" "hayday_tracker.old.db" -Force
Copy-Item "C:\path\to\HayDayTracker-backup-20261123-0900.sqlite" "$dir\hayday_tracker.db"
```

## Check it works

```powershell
py -3 tests\verify_workflow.py
py -3 tests\verify_dialogs.py
py -3 tests\verify_v101.py
```

This runs the whole workflow against a temporary database (never your real data): partial saves, reopening a week,
correcting a past entry, renaming and archiving without losing history, true zeros, missing baselines, counter resets,
ties, CSV export and backup/restore.

## Files

```
HayDayTracker.bat            double-click launcher
HayDayTracker (show errors).bat   same, with a visible console for troubleshooting
hayday_tracker/              the app (db.py storage, scoring.py rules, ui_*.py screens)
tests/verify_workflow.py     end-to-end check (rules, grid, rankings)
tests/verify_dialogs.py      dialogs, export, backup button, counter-reset flow
tests/verify_v101.py         scrolling, tab style, Derby, and the 1.0.0 -> 1.0.1 database upgrade
```

If something unexpected goes wrong inside the app, a message appears and the details are appended to
`%LOCALAPPDATA%\HayDayTracker\error.log`.

## Upgrading from 1.0.0

Replace the files and start the app. Your database is upgraded automatically: it gains two Derby columns and nothing
is changed or removed. Before that happens, a copy is saved next to it as
`%LOCALAPPDATA%\HayDayTracker\hayday_tracker.before-derby.bak`. Backups made by 1.0.0 can still be restored in 1.0.1.

## What changed in 1.0.1

* **Fixed:** the Monday Update list could not be scrolled (mouse wheel or scroll bar) when neighbours were added after the
  window had opened. It also now scrolls with touchpad wheels.
* **Changed:** the selected tab (Overview / Monday Update / Neighbours / Rankings) now only turns light green. Its size no
  longer changes.
* **Added:** Derby scores: a Derby column in Monday Update, Rankings, the Overview and each neighbour's history, Derby
  settings, and both CSV exports.
