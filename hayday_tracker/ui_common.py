"""Shared look and feel, small reusable widgets and dialog helpers."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from datetime import date
from tkinter import ttk

from .util import fmt_date

FONT = "Segoe UI"

C = {
    "bg": "#F4EFE3",        # warm cream
    "card": "#FFFCF5",
    "border": "#DCD2BA",
    "tab": "#E6DEC9",
    "tab_selected": "#BFD8B4",   # light green for the active tab
    "trough": "#EAE3D0",
    "btn": "#E8E0CB",
    "btn_active": "#DDD3B9",
    "green": "#4C7A4B",
    "green_dark": "#33573A",
    "green_light": "#DCE8D3",
    "wheat": "#D8B968",
    "text": "#2F2B25",
    "muted": "#7B7467",
    "error": "#B3402F",
    "error_bg": "#F8DAD4",
    "warn": "#9A6512",
    "warn_bg": "#FBEBC9",
    "ok": "#3F7A45",
    "entry": "#FFFFFF",
}


def apply_theme(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        tkfont.nametofont(name).configure(family=FONT, size=10)
    root.configure(bg=C["bg"])
    root.option_add("*TCombobox*Listbox.background", C["entry"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["green_light"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["text"])
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    style.configure(".", background=C["bg"], foreground=C["text"], font=(FONT, 10),
                    bordercolor=C["border"], lightcolor=C["bg"], darkcolor=C["bg"],
                    troughcolor=C["trough"], focuscolor=C["green"], relief="flat")
    style.configure("TFrame", background=C["bg"])
    style.configure("Card.TFrame", background=C["card"])
    style.configure("Banner.TFrame", background=C["green_dark"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"])
    style.configure("Card.TLabel", background=C["card"])
    style.configure("Muted.TLabel", foreground=C["muted"])
    style.configure("CardMuted.TLabel", background=C["card"], foreground=C["muted"])
    style.configure("Title.TLabel", font=(FONT, 20, "bold"), foreground=C["green_dark"])
    style.configure("Heading.TLabel", font=(FONT, 13, "bold"), foreground=C["green_dark"])
    style.configure("CardHeading.TLabel", background=C["card"], font=(FONT, 12, "bold"),
                    foreground=C["green_dark"])
    style.configure("Big.TLabel", background=C["card"], font=(FONT, 24, "bold"), foreground=C["text"])
    style.configure("Small.TLabel", font=(FONT, 9), foreground=C["muted"])
    style.configure("Banner.TLabel", background=C["green_dark"], foreground="#FFFFFF",
                    font=(FONT, 15, "bold"))
    style.configure("BannerSub.TLabel", background=C["green_dark"], foreground="#CFE0C5", font=(FONT, 9))
    style.configure("Good.TLabel", foreground=C["ok"])
    style.configure("Bad.TLabel", foreground=C["error"])
    style.configure("Warn.TLabel", foreground=C["warn"])
    style.configure("CardGood.TLabel", background=C["card"], foreground=C["ok"])
    style.configure("CardBad.TLabel", background=C["card"], foreground=C["error"])
    style.configure("CardWarn.TLabel", background=C["card"], foreground=C["warn"])

    style.configure("TButton", background=C["btn"], foreground=C["text"], padding=(14, 7),
                    borderwidth=1, bordercolor=C["border"], focusthickness=1)
    style.map("TButton", background=[("active", C["btn_active"]), ("disabled", C["trough"])],
              foreground=[("disabled", C["muted"])])
    style.configure("Primary.TButton", background=C["green"], foreground="#FFFFFF",
                    bordercolor=C["green_dark"], font=(FONT, 10, "bold"))
    style.map("Primary.TButton", background=[("active", C["green_dark"]), ("disabled", "#A9BFA5")],
              foreground=[("disabled", "#F4F4F4")])
    style.configure("Danger.TButton", foreground=C["error"])
    style.configure("Banner.TButton", background="#4A7452", foreground="#FFFFFF",
                    bordercolor="#6E9A74", padding=(12, 6))
    style.map("Banner.TButton", background=[("active", "#5E8A66")])
    style.configure("Banner.TMenubutton", background="#4A7452", foreground="#FFFFFF",
                    bordercolor="#6E9A74", padding=(12, 6), arrowcolor="#FFFFFF")
    style.map("Banner.TMenubutton", background=[("active", "#5E8A66")])
    style.configure("Nav.TButton", padding=(8, 5))

    style.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(0, 8, 0, 0))
    # Selecting a tab only changes its colour: same padding, same size, nothing shifts or grows.
    style.configure("TNotebook.Tab", background=C["tab"], foreground=C["muted"], padding=(24, 10),
                    font=(FONT, 11, "bold"), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", C["tab_selected"]), ("active", C["btn_active"])],
              foreground=[("selected", C["green_dark"])],
              padding=[("selected", (24, 10)), ("!selected", (24, 10))],
              expand=[("selected", (0, 0, 0, 0)), ("!selected", (0, 0, 0, 0))])

    style.configure("Treeview", background=C["card"], fieldbackground=C["card"], rowheight=30,
                    borderwidth=0, font=(FONT, 10))
    style.map("Treeview", background=[("selected", C["green_light"])],
              foreground=[("selected", C["text"])])
    style.configure("Treeview.Heading", background="#E9E1CD", foreground=C["text"],
                    font=(FONT, 10, "bold"), padding=(8, 8), relief="flat")
    style.map("Treeview.Heading", background=[("active", C["btn_active"])])

    style.configure("TEntry", fieldbackground=C["entry"], padding=5, bordercolor=C["border"],
                    lightcolor=C["entry"], darkcolor=C["entry"])
    style.map("TEntry", bordercolor=[("focus", C["green"])], lightcolor=[("focus", C["green"])],
              fieldbackground=[("disabled", "#EFE9DA")], foreground=[("disabled", C["text"])])
    style.configure("Invalid.TEntry", fieldbackground=C["error_bg"], bordercolor=C["error"],
                    lightcolor=C["error_bg"], darkcolor=C["error_bg"], padding=5)
    style.map("Invalid.TEntry", bordercolor=[("focus", C["error"])],
              lightcolor=[("focus", C["error"])], fieldbackground=[("focus", C["error_bg"])])
    style.configure("Warn.TEntry", fieldbackground=C["warn_bg"], bordercolor=C["warn"],
                    lightcolor=C["warn_bg"], darkcolor=C["warn_bg"], padding=5)
    style.map("Warn.TEntry", bordercolor=[("focus", C["green"])], fieldbackground=[("focus", C["warn_bg"])])
    style.configure("TCombobox", fieldbackground=C["entry"], padding=5, arrowcolor=C["green_dark"],
                    bordercolor=C["border"], lightcolor=C["entry"], darkcolor=C["entry"])
    style.map("TCombobox", fieldbackground=[("readonly", C["entry"])], bordercolor=[("focus", C["green"])])
    style.configure("TCheckbutton", background=C["bg"])
    style.configure("TRadiobutton", background=C["bg"])
    style.configure("TLabelframe", background=C["bg"], bordercolor=C["border"])
    style.configure("TLabelframe.Label", background=C["bg"], foreground=C["green_dark"],
                    font=(FONT, 10, "bold"))
    style.configure("Horizontal.TProgressbar", troughcolor=C["trough"], background=C["green"],
                    bordercolor=C["border"], lightcolor=C["green"], darkcolor=C["green"], thickness=14)
    style.configure("TScrollbar", background="#CFC6AE", troughcolor="#EFE8D6", bordercolor=C["border"],
                    arrowcolor=C["muted"])
    style.configure("TSeparator", background=C["border"])
    style.configure("TPanedwindow", background=C["bg"])
    return style


def make_card(parent, padding: int = 14) -> tuple[tk.Frame, ttk.Frame]:
    """A cream panel with a thin border. Returns ``(outer, inner)``; grid/pack the outer one."""
    outer = tk.Frame(parent, bg=C["border"])
    inner = ttk.Frame(outer, style="Card.TFrame", padding=padding)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return outer, inner


def make_window_icon(root: tk.Tk) -> None:
    """A tiny hand-drawn icon (a wheat-gold sun over a green field)."""
    try:
        img = tk.PhotoImage(width=32, height=32)
        img.put(C["green_dark"], to=(0, 0, 32, 32))
        img.put(C["green"], to=(0, 20, 32, 32))
        for y in range(4, 18):
            half = int((49 - (y - 11) ** 2) ** 0.5) if abs(y - 11) <= 7 else 0
            if half:
                img.put(C["wheat"], to=(16 - half, y, 16 + half, y + 1))
        img.put("#8FB27F", to=(0, 24, 32, 26))
        root.iconphoto(True, img)
        root._icon_ref = img  # keep a reference so it is not garbage collected
    except tk.TclError:
        pass


# ------------------------------------------------------------------ scrolling
def enable_mousewheel(root: tk.Misc) -> None:
    """Make the mouse wheel scroll whichever ScrollFrame the pointer is over."""
    def on_wheel(event):
        try:
            w = root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None:
            if isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox, ttk.Combobox)):
                return
            target = getattr(w, "_wheel_target", None)
            if target is not None:
                # Smooth touchpads send deltas smaller than 120, so never round a scroll down to nothing.
                steps = -event.delta / 60
                steps = int(steps) if abs(steps) >= 1 else (1 if steps > 0 else -1)
                target.yview_scroll(steps, "units")
                return
            w = getattr(w, "master", None)

    root.bind_all("<MouseWheel>", on_wheel)


class ScrollFrame(ttk.Frame):
    """A vertically scrolling area. Put content in ``.inner``."""

    def __init__(self, parent, background: str = C["card"], inner_style: str = "Card.TFrame"):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=background, yscrollincrement=28)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, style=inner_style)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas._wheel_target = self.canvas
        self._applied: tuple[int, int] = (0, 0)
        self.inner.bind("<Configure>", lambda e: self._fit())
        self.canvas.bind("<Configure>", lambda e: self._fit())
        self._poll()

    def _fit(self) -> None:
        """Match the canvas width and be at least as tall as the canvas, so expanding children can grow."""
        width = self.canvas.winfo_width()
        height = max(self.canvas.winfo_height(), self.inner.winfo_reqheight())
        if (width, height) == self._applied:
            return
        self._applied = (width, height)
        self.canvas.itemconfigure(self._window, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _poll(self) -> None:
        """Re-check the content height a few times a second.

        Because the inner frame is pinned to an explicit height, Tk sends no <Configure> event when
        its content later grows (for example when rows are added). Without this check the scroll
        region would stay at the old height and nothing could be scrolled.
        """
        try:
            self._fit()
            self.after(250, self._poll)
        except tk.TclError:      # the widget was destroyed
            pass

    def refit(self) -> None:
        """Recalculate straight away (call after rebuilding the content)."""
        self.update_idletasks()
        self._fit()

    def scrollbar_width(self) -> int:
        return self.scrollbar.winfo_reqwidth()

    def see(self, widget: tk.Misc) -> None:
        """Scroll just enough to bring ``widget`` into view."""
        self.refit()
        total = max(self._applied[1], 1)
        top = self.canvas.canvasy(0)
        view = self.canvas.winfo_height()
        y, h = widget.winfo_y(), widget.winfo_height()
        parent = widget.master
        while parent is not None and parent is not self.inner:
            y += parent.winfo_y()
            parent = parent.master
        if y < top:
            self.canvas.yview_moveto(max(0.0, (y - 4) / total))
        elif y + h > top + view:
            self.canvas.yview_moveto(max(0.0, (y + h + 4 - view) / total))


# ---------------------------------------------------------------- week picker
class WeekPicker(ttk.Frame):
    """Previous / drop-down / next control for choosing a reporting Monday."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._by_label: dict[str, date] = {}
        self._labels: list[str] = []
        self._weeks: list[date] = []
        ttk.Button(self, text="‹", width=3, style="Nav.TButton",
                   command=lambda: self._step(+1)).pack(side="left")
        self.combo = ttk.Combobox(self, state="readonly", width=31, font=(FONT, 10, "bold"))
        self.combo.pack(side="left", padx=4)
        ttk.Button(self, text="›", width=3, style="Nav.TButton",
                   command=lambda: self._step(-1)).pack(side="left")
        ttk.Button(self, text="Latest", style="Nav.TButton",
                   command=lambda: app.request_week(app.latest_monday())).pack(side="left", padx=(6, 0))
        self.combo.bind("<<ComboboxSelected>>", self._chosen)
        self.refresh()

    def refresh(self) -> None:
        self._weeks = self.app.week_options()
        data = set(self.app.data_weeks())
        current = self.app.latest_monday()
        self._labels = []
        self._by_label = {}
        for w in self._weeks:
            label = fmt_date(w) + ("   ✓" if w in data else "") + ("   (open)" if w == current else "")
            self._labels.append(label)
            self._by_label[label] = w
        self.combo.configure(values=self._labels)
        if self.app.week in self._weeks:
            self.combo.current(self._weeks.index(self.app.week))

    def _chosen(self, _event=None) -> None:
        week = self._by_label.get(self.combo.get())
        if week is not None:
            self.app.request_week(week)
        self.refresh()

    def _step(self, direction: int) -> None:
        """direction +1 goes to the earlier Monday, -1 to the later one."""
        if self.app.week not in self._weeks:
            return
        i = self._weeks.index(self.app.week) + direction
        if 0 <= i < len(self._weeks):
            self.app.request_week(self._weeks[i])


# -------------------------------------------------------------------- dialogs
class Dialog(tk.Toplevel):
    """A modal dialog with a padded body frame. Call ``show()`` to run it."""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=C["bg"])
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result = None
        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self):
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.wait_window(self)
        return self.result
