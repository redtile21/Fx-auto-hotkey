"""Main window, pages and dialogs."""
from __future__ import annotations

import copy
import os
import re
import sys
import time

from PySide6.QtCore import QFileInfo, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFileIconProvider, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QSystemTrayIcon, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import __version__, config, keys, macapi, palette, theme
from .config import Profile, Shortcut
from .widgets import GradientText, HotkeyEdit, SchemeCard, Switch, badge_pixmap

CHECKED, UNCHECKED = Qt.CheckState.Checked, Qt.CheckState.Unchecked
ROLE = Qt.ItemDataRole.UserRole


# ------------------------------------------------------------------ helpers
def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def app_pixmap(size: int) -> QPixmap:
    pm = QPixmap(resource_path(os.path.join("assets", "icon.png")))
    if pm.isNull():
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
    return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


def app_icon() -> QIcon:
    p = resource_path(os.path.join("assets", "icon.png"))
    return QIcon(p) if os.path.exists(p) else QIcon(app_pixmap(64))


def tray_icon() -> QIcon:
    """Monochrome template icon so it fits the macOS menu bar (light & dark)."""
    p = resource_path(os.path.join("assets", "tray.png"))
    if not os.path.exists(p):
        return app_icon()
    icon = QIcon(p)
    icon.setIsMask(True)
    return icon


_icon_cache: dict = {}


def profile_icon(p: Profile, size: int) -> QPixmap:
    """The app's own icon (from its .app bundle) or a letter badge when unknown."""
    path = p.exe_path
    if path and os.path.exists(path):
        key = (path, size)
        if key not in _icon_cache:
            pm = QFileIconProvider().icon(QFileInfo(path)).pixmap(QSize(size, size))
            _icon_cache[key] = None if pm.isNull() else pm.scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if _icon_cache[key] is not None:
            return _icon_cache[key]
    return badge_pixmap(p.name, size)


def make_card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def muted(text: str, wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("muted")
    lb.setWordWrap(wrap)
    return lb


def scrolled(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(inner)
    return sa


STEPS_HELP = ("One step per line:   key {CLEAR}   \u00b7   type {TEXT}   \u00b7   wait 500   \u00b7   click\n"
              "{TEXT} = shortcut text.   {CLEAR} = clear-filters key (set per program).   # comments ignored.")


def check_steps_label(label: QLabel, text: str, clear_key: str = "ctrl+tab") -> None:
    n, err = keys.validate_steps(keys.resolve_steps(text, clear_key))
    if err:
        label.setObjectName("err")
        label.setText(err)
    else:
        label.setObjectName("okmsg")
        label.setText(f"\u2713  {n} step{'s' if n != 1 else ''}")
    label.style().unpolish(label)
    label.style().polish(label)


class Bridge(QObject):
    log = Signal(object)


# ------------------------------------------------------------------ dialogs
class PickWindowDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Pick a running app")
        self.resize(640, 520)
        self.exe = ""
        self.title = ""
        self.path = ""
        self.use_title = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(GradientText("Open windows", 15))
        lay.addWidget(muted("Open the app first, then choose it from the list. "
                            "Window titles appear once FX Hotkeys has the Accessibility permission."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.textChanged.connect(self._fill)
        lay.addWidget(self.search)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["App", "Window title"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._ok)
        lay.addWidget(self.table, 1)
        self.chk = QCheckBox("Also match the window title (useful when one program has many windows)")
        lay.addWidget(self.chk)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._load)
        row.addWidget(refresh)
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Select")
        ok.setObjectName("primary")
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self._items = []
        self._load()

    def _load(self) -> None:
        self._items = macapi.list_windows_full()
        self._fill()

    def _fill(self) -> None:
        q = self.search.text().strip().lower()
        rows = [(e, t, pth) for e, t, pth in self._items if not q or q in e.lower() or q in t.lower()]
        self.table.setRowCount(len(rows))
        for r, (e, t, pth) in enumerate(rows):
            it = QTableWidgetItem(e)
            it.setData(ROLE, pth)
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, QTableWidgetItem(t))

    def _ok(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        self.exe = self.table.item(r, 0).text()
        self.path = self.table.item(r, 0).data(ROLE) or ""
        self.title = self.table.item(r, 1).text()
        self.use_title = self.chk.isChecked()
        self.accept()


class ShortcutDialog(QDialog):
    def __init__(self, win: "MainWindow", profile: Profile, sc: Shortcut | None):
        super().__init__(win)
        self.win, self.profile = win, profile
        self.setWindowTitle("Edit shortcut" if sc else "New shortcut")
        self.setMinimumWidth(580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(8)
        lay.addWidget(GradientText("Edit shortcut" if sc else "New shortcut", 15))
        lay.addSpacing(4)

        lay.addWidget(QLabel("Hotkey"))
        self.hk = HotkeyEdit(win.engine, sc.hotkey if sc else "")
        lay.addWidget(self.hk)
        lay.addWidget(muted("Tip: \u2318 Cmd + Tab, \u2318 Cmd + Space and other system shortcuts are "
                            "handled by macOS first and can't be used here."))

        lay.addWidget(QLabel("Text to type   (goes where {TEXT} appears in the steps)"))
        self.e_text = QLineEdit(sc.text if sc else "")
        lay.addWidget(self.e_text)
        lay.addWidget(QLabel("Note   (optional, only for you)"))
        self.e_note = QLineEdit(sc.note if sc else "")
        lay.addWidget(self.e_note)

        custom = bool(sc and sc.steps.strip())
        self.chk = QCheckBox("Use custom steps for this shortcut  (otherwise the program's default steps)")
        self.chk.setChecked(custom)
        lay.addSpacing(4)
        lay.addWidget(self.chk)
        self.steps = QPlainTextEdit()
        self.steps.setObjectName("code")
        self.steps.setFixedHeight(130)
        self.steps.setPlainText(sc.steps if custom else profile.steps)
        self.steps.setEnabled(custom)
        lay.addWidget(self.steps)
        self.check = QLabel()
        lay.addWidget(self.check)
        lay.addWidget(muted(STEPS_HELP))
        self.chk.toggled.connect(self._toggle)
        self.steps.textChanged.connect(self._validate)
        self._validate()

        row = QHBoxLayout()
        row.setSpacing(8)
        self.test_btn = QPushButton("Test in 3 seconds")
        self.test_btn.clicked.connect(self._test)
        self.test_lbl = QLabel("")
        self.test_lbl.setObjectName("muted")
        row.addWidget(self.test_btn)
        row.addWidget(self.test_lbl)
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        lay.addSpacing(6)
        lay.addLayout(row)

    def _toggle(self, on: bool) -> None:
        self.steps.setEnabled(on)
        if not on:
            self.steps.setPlainText(self.profile.steps)

    def _validate(self) -> None:
        check_steps_label(self.check, self.steps.toPlainText(), self.profile.clear_key)

    def values(self) -> dict:
        return {"hotkey": self.hk.value(), "text": self.e_text.text(), "note": self.e_note.text().strip(),
                "steps": self.steps.toPlainText().strip() if self.chk.isChecked() else ""}

    def _save(self) -> None:
        v = self.values()
        if not keys.parse_hotkey(v["hotkey"]):
            QMessageBox.warning(self, "Hotkey", "Please record a hotkey first.")
            return
        if self.chk.isChecked():
            n, err = keys.validate_steps(keys.resolve_steps(v["steps"], self.profile.clear_key))
            if err or n == 0:
                QMessageBox.warning(self, "Steps", err or "Add at least one step.")
                return
        self.accept()

    def _test(self) -> None:
        v = self.values()
        tmp = Shortcut(hotkey=v["hotkey"], text=v["text"], steps=v["steps"])
        _, err = keys.validate_steps(
            keys.resolve_steps(v["steps"] or self.profile.steps, self.profile.clear_key))
        if err:
            QMessageBox.warning(self, "Steps", err)
            return
        self.win.engine.test_run(self.profile, tmp, 3.0)
        self._left = 3
        self.test_btn.setEnabled(False)
        self._tick()

    def _tick(self) -> None:
        if self._left > 0:
            self.test_lbl.setText(f"Switch to the program...  {self._left}")
            self._left -= 1
            QTimer.singleShot(1000, self._tick)
        else:
            self.test_lbl.setText("Sent.")
            self.test_btn.setEnabled(True)


# ------------------------------------------------------------------ pages
class ProfilePage(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.p: Profile | None = None
        self._loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 18)
        root.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("hero")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(26, 20, 26, 20)
        hl.setSpacing(16)
        box = QFrame()
        box.setObjectName("iconbox")
        box.setFixedSize(60, 60)
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        self.h_icon = QLabel()
        self.h_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self.h_icon)
        hl.addWidget(box)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.h_name = QLabel()
        self.h_name.setObjectName("h1")
        self.h_sub = QLabel()
        self.h_sub.setObjectName("sub")
        col.addWidget(self.h_name)
        col.addWidget(self.h_sub)
        hl.addLayout(col, 1)
        hl.addWidget(QLabel("Enabled"))
        self.sw_on = Switch()
        self.sw_on.toggled.connect(self._on_enabled)
        hl.addWidget(self.sw_on)
        root.addWidget(hero)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_shortcuts(), "Shortcuts")
        self.tabs.addTab(scrolled(self._build_program()), "Program")
        self.tabs.addTab(scrolled(self._build_autosave()), "Auto-save")
        root.addWidget(self.tabs, 1)

    # ---- shortcuts tab
    def _build_shortcuts(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search shortcuts...")
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self.refresh_table)
        bar.addWidget(self.search)
        bar.addStretch()
        for text, slot, name in (("Duplicate", self._dup, ""), ("Delete", self._delete, "danger"),
                                 ("Edit", self._edit, ""), ("+  Add shortcut", self._add, "primary")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(slot)
            bar.addWidget(b)
        lay.addLayout(bar)

        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 6, 10, 10)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["On", "Hotkey", "Text / note", "Steps"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 54)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 200)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 150)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._item_changed)
        self.table.doubleClicked.connect(self._edit)
        cl.addWidget(self.table)
        self.empty = muted("No shortcuts yet \u2014 press \u201cAdd shortcut\u201d to create your first one.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.empty)
        lay.addWidget(card, 1)
        return w

    def refresh_table(self) -> None:
        if not self.p:
            return
        q = self.search.text().strip().lower()
        counts = {}
        for s in self.p.shortcuts:
            if s.enabled and s.hotkey:
                counts[s.hotkey] = counts.get(s.hotkey, 0) + 1
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        dim = self.palette().color(self.palette().ColorRole.PlaceholderText)
        for sc in self.p.shortcuts:
            if q and q not in f"{sc.hotkey} {keys.pretty_hotkey(sc.hotkey)} {sc.text} {sc.note}".lower():
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | flags)
            chk.setCheckState(CHECKED if sc.enabled else UNCHECKED)
            chk.setData(ROLE, sc.id)
            dup = counts.get(sc.hotkey, 0) > 1 and sc.enabled
            hk = QTableWidgetItem(("\u26a0  " if dup else "") + (keys.pretty_hotkey(sc.hotkey) or "(none)"))
            if dup:
                hk.setToolTip("Another shortcut in this program uses the same hotkey")
            txt = QTableWidgetItem(sc.text + (f"    \u2014 {sc.note}" if sc.note else ""))
            st = QTableWidgetItem("Custom" if sc.steps.strip() else "Program default")
            for it in (hk, txt, st):
                it.setFlags(flags)
                it.setData(ROLE, sc.id)
                if not sc.enabled:
                    it.setForeground(dim)
            self.table.setItem(r, 0, chk)
            self.table.setItem(r, 1, hk)
            self.table.setItem(r, 2, txt)
            self.table.setItem(r, 3, st)
        self.table.blockSignals(False)
        self.empty.setVisible(not self.p.shortcuts)

    def _selected(self) -> Shortcut | None:
        r = self.table.currentRow()
        if r < 0 or not self.p:
            return None
        sid = self.table.item(r, 1).data(ROLE)
        return next((s for s in self.p.shortcuts if s.id == sid), None)

    def _item_changed(self, item) -> None:
        if item.column() != 0 or not self.p:
            return
        sc = next((s for s in self.p.shortcuts if s.id == item.data(ROLE)), None)
        if sc:
            sc.enabled = item.checkState() == CHECKED
            self.win.commit()
            QTimer.singleShot(0, self.refresh_table)

    def _add(self) -> None:
        if not self.p:
            return
        dlg = ShortcutDialog(self.win, self.p, None)
        if dlg.exec():
            self.p.shortcuts.append(Shortcut(**dlg.values()))
            self.win.commit()
            self.refresh_table()

    def _edit(self, *_a) -> None:
        sc = self._selected()
        if not sc:
            return
        dlg = ShortcutDialog(self.win, self.p, sc)
        if dlg.exec():
            for k, v in dlg.values().items():
                setattr(sc, k, v)
            self.win.commit()
            self.refresh_table()

    def _dup(self) -> None:
        sc = self._selected()
        if not sc:
            return
        new = copy.copy(sc)
        new.id = config._id()
        new.hotkey = ""
        new.enabled = False             # stays off until it gets its own hotkey
        self.p.shortcuts.insert(self.p.shortcuts.index(sc) + 1, new)
        self.win.commit()
        self.refresh_table()

    def _delete(self) -> None:
        sc = self._selected()
        if not sc:
            return
        label = sc.text or keys.pretty_hotkey(sc.hotkey) or "this shortcut"
        if QMessageBox.question(self, "Delete", f"Delete \u201c{label}\u201d?") == QMessageBox.StandardButton.Yes:
            self.p.shortcuts.remove(sc)
            self.win.commit()
            self.refresh_table()

    # ---- program tab
    def _build_program(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 8)
        card = make_card()
        g = QGridLayout(card)
        g.setContentsMargins(24, 22, 24, 22)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(10)
        g.setColumnStretch(1, 1)
        r = 0

        g.addWidget(QLabel("Name"), r, 0)
        self.e_name = QLineEdit()
        self.e_name.textEdited.connect(self._on_name)
        g.addWidget(self.e_name, r, 1, 1, 2)
        r += 1
        g.addWidget(QLabel("App name"), r, 0)
        self.e_exe = QLineEdit()
        self.e_exe.setPlaceholderText("e.g. Bitwig Studio   (several: separate with commas)")
        self.e_exe.textEdited.connect(self._on_match)
        g.addWidget(self.e_exe, r, 1)
        pr = QHBoxLayout()
        pr.setSpacing(6)
        pick = QPushButton("Pick from open apps...")
        pick.clicked.connect(self._pick)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        pr.addWidget(pick)
        pr.addWidget(browse)
        g.addLayout(pr, r, 2)
        r += 1
        g.addWidget(QLabel("Window title contains"), r, 0)
        self.e_title = QLineEdit()
        self.e_title.setPlaceholderText("e.g. Bitwig Studio")
        self.e_title.textEdited.connect(self._on_match)
        g.addWidget(self.e_title, r, 1, 1, 2)
        r += 1
        g.addWidget(muted("Leave both empty to make these shortcuts work in every program."), r, 1, 1, 2)
        r += 1

        g.addWidget(QLabel("Typing mode"), r, 0)
        self.cb_typing = QComboBox()
        self.cb_typing.addItem("Keys \u2014 follows the active keyboard layout", "keys")
        self.cb_typing.addItem("Unicode \u2014 works with any layout / language", "unicode")
        self.cb_typing.currentIndexChanged.connect(self._on_typing)
        g.addWidget(self.cb_typing, r, 1, 1, 2)
        r += 1
        g.addWidget(QLabel("Delay between steps"), r, 0)
        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(0, 5000)
        self.sp_delay.setSingleStep(50)
        self.sp_delay.setSuffix(" ms")
        self.sp_delay.setMaximumWidth(140)
        self.sp_delay.valueChanged.connect(self._on_delay)
        g.addWidget(self.sp_delay, r, 1)
        r += 1

        g.addWidget(QLabel("Clear filters key"), r, 0)
        self.hk_clear = HotkeyEdit(self.win.engine, "ctrl+tab")
        self.hk_clear.changed.connect(self._on_clear_key)
        g.addWidget(self.hk_clear, r, 1, 1, 2)
        r += 1
        g.addWidget(muted("Replaces {CLEAR} in the steps (e.g. Bitwig clear-all-filters). "
                          "Change it if your DAW uses a different shortcut."), r, 1, 1, 2)
        r += 1

        g.addWidget(QLabel("Default steps"), r, 0, Qt.AlignmentFlag.AlignTop)
        self.e_steps = QPlainTextEdit()
        self.e_steps.setObjectName("code")
        self.e_steps.setFixedHeight(150)
        self.e_steps.textChanged.connect(self._on_steps)
        g.addWidget(self.e_steps, r, 1, 1, 2)
        r += 1
        self.steps_check = QLabel()
        g.addWidget(self.steps_check, r, 1, 1, 2)
        r += 1
        g.addWidget(muted(STEPS_HELP), r, 1, 1, 2)
        r += 1
        lay.addWidget(card)

        dele = QPushButton("Delete this program")
        dele.setObjectName("danger")
        dele.clicked.connect(lambda: self.win.delete_profile(self.p))
        row = QHBoxLayout()
        row.addWidget(dele)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return w

    # ---- auto-save tab
    def _build_autosave(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 8)
        card = make_card()
        g = QGridLayout(card)
        g.setContentsMargins(24, 22, 24, 22)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(12)
        g.setColumnStretch(2, 1)
        g.addWidget(QLabel("Enable auto-save"), 0, 0)
        self.sw_auto = Switch()
        self.sw_auto.toggled.connect(self._on_auto)
        g.addWidget(self.sw_auto, 0, 1)
        g.addWidget(QLabel("Every"), 1, 0)
        self.sp_every = QSpinBox()
        self.sp_every.setRange(5, 86400)
        self.sp_every.setSuffix(" seconds")
        self.sp_every.setMaximumWidth(170)
        self.sp_every.valueChanged.connect(self._on_every)
        g.addWidget(self.sp_every, 1, 1)
        g.addWidget(QLabel("Key to send"), 2, 0)
        self.hk_save = HotkeyEdit(self.win.engine, "ctrl+s")
        self.hk_save.changed.connect(self._on_savekey)
        g.addWidget(self.hk_save, 2, 1, 1, 2)
        g.addWidget(muted("Sends the key at that interval, but only while a window of this program is in front. "
                          "Needs the program rule (name or title) to be set, so it never saves in the wrong app."),
                    3, 0, 1, 3)
        lay.addWidget(card)
        lay.addStretch()
        return w

    # ---- load / handlers
    def set_profile(self, p: Profile | None) -> None:
        self.p = p
        if not p:
            return
        self._loading = True
        self.h_name.setText(p.name)
        self.h_sub.setText(p.describe())
        self.refresh_header_icon()
        self.sw_on.setChecked(p.enabled)
        self.e_name.setText(p.name)
        self.e_exe.setText(p.exe)
        self.e_title.setText(p.title)
        self.cb_typing.setCurrentIndex(max(0, self.cb_typing.findData(p.typing)))
        self.sp_delay.setValue(p.delay_ms)
        self.hk_clear.setValue(p.clear_key or "ctrl+tab")
        self.e_steps.setPlainText(p.steps)
        check_steps_label(self.steps_check, p.steps, p.clear_key)
        self.sw_auto.setChecked(p.autosave)
        self.sp_every.setValue(p.autosave_every)
        self.hk_save.setValue(p.autosave_key)
        self._loading = False
        self.search.clear()
        self.refresh_table()

    def refresh_header_icon(self) -> None:
        if self.p:
            self.h_icon.setPixmap(profile_icon(self.p, 40))

    def _on_enabled(self, on):
        if self._loading or not self.p:
            return
        self.p.enabled = on
        self.win.update_profile_item(self.p)
        self.win.commit()

    def _on_name(self, text):
        if self._loading or not self.p:
            return
        self.p.name = text.strip() or "Unnamed"
        self.h_name.setText(self.p.name)
        self.win.update_profile_item(self.p)
        self.win.commit()

    def _on_match(self, _t=""):
        if self._loading or not self.p:
            return
        self.p.exe, self.p.title = self.e_exe.text().strip(), self.e_title.text().strip()
        names = {config._norm_exe(x) for x in self.p.exe.split(",") if x.strip()}
        if self.p.exe_path and names and config._norm_exe(os.path.basename(self.p.exe_path)) not in names:
            self.p.exe_path = ""                      # stale icon source: the program changed
            self.refresh_header_icon()
            self.win.update_profile_item(self.p)
        self.h_sub.setText(self.p.describe())
        self.win.commit()

    def _pick(self):
        dlg = PickWindowDialog(self.win)
        if dlg.exec():
            self.e_exe.setText(dlg.exe)
            self.e_title.setText(dlg.title if dlg.use_title else "")
            if self.p and self.p.name in ("New program", "Unnamed"):
                self.e_name.setText(dlg.exe)
                self._on_name(self.e_name.text())
            self._on_match()
            if self.p:
                self.p.exe_path = dlg.path
                self._icon_changed()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the app", "/Applications", "Applications (*.app)")
        if not path or not self.p:
            return
        path = path.rstrip("/")
        base = os.path.basename(path)
        base = base[:-4] if base.lower().endswith(".app") else base
        self.e_exe.setText(base)
        if self.p.name in ("New program", "Unnamed"):
            self.e_name.setText(base)
            self._on_name(self.e_name.text())
        self._on_match()
        self.p.exe_path = path
        self._icon_changed()

    def _icon_changed(self):
        self.refresh_header_icon()
        self.win.update_profile_item(self.p)
        self.win.commit()

    def _on_typing(self, _i):
        if not self._loading and self.p:
            self.p.typing = self.cb_typing.currentData()
            self.win.commit()

    def _on_delay(self, v):
        if not self._loading and self.p:
            self.p.delay_ms = v
            self.win.commit()

    def _on_clear_key(self, hk: str):
        if self._loading or not self.p or not hk:
            return
        old = self.p.clear_key or "ctrl+tab"
        self.p.clear_key = hk
        # Keep literal key lines in steps in sync when the user had written the old key
        if old != hk:
            def _swap(text: str) -> str:
                return re.sub(
                    rf"(?im)^(\s*key\s+){re.escape(old)}(\s*)$",
                    rf"\1{hk}\2",
                    text,
                )
            self.p.steps = _swap(self.p.steps)
            for sc in self.p.shortcuts:
                if sc.steps.strip():
                    sc.steps = _swap(sc.steps)
            self._loading = True
            self.e_steps.setPlainText(self.p.steps)
            self._loading = False
        check_steps_label(self.steps_check, self.p.steps, self.p.clear_key)
        self.win.commit()

    def _on_steps(self):
        if self._loading or not self.p:
            return
        self.p.steps = self.e_steps.toPlainText()
        check_steps_label(self.steps_check, self.p.steps, self.p.clear_key)
        self.win.commit()

    def _on_auto(self, on):
        if not self._loading and self.p:
            self.p.autosave = on
            self.win.commit()

    def _on_every(self, v):
        if not self._loading and self.p:
            self.p.autosave_every = v
            self.win.commit()

    def _on_savekey(self, hk):
        if not self._loading and self.p:
            self.p.autosave_key = hk
            self.win.commit()


class ActivityPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(GradientText("Activity", 20))
        head.addStretch()
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.list.clear())
        head.addWidget(clear)
        lay.addLayout(head)
        lay.addWidget(muted("Every shortcut that fires shows up here \u2014 handy for checking that it hit the right program."))
        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 8, 8, 8)
        self.list = QListWidget()
        self.list.setObjectName("log")
        cl.addWidget(self.list)
        lay.addWidget(card, 1)

    def add(self, e: dict) -> None:
        ok = not e.get("error")
        text = (f"{e['time']}    {e['profile']}    \u00b7    {keys.pretty_hotkey(e['hotkey'])}"
                f"    \u00b7    {e['label']}    " + ("\u2713" if ok else f"\u2717  {e['error']}"))
        self.list.insertItem(0, text)
        while self.list.count() > 300:
            self.list.takeItem(self.list.count() - 1)


class SettingsPage(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        s = win.cfg.settings
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 18)
        lay.setSpacing(14)
        lay.addWidget(GradientText("Settings", 20))

        # appearance
        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(10)
        t = QLabel("Appearance")
        t.setObjectName("h2")
        cl.addWidget(t)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for label, mode in (("System", "system"), ("Light", "light"), ("Dark", "dark")):
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(s.theme == mode)
            b.clicked.connect(lambda _c=False, m=mode: self._set_theme(m))
            self.group.addButton(b)
            row.addWidget(b)
        row.addStretch()
        cl.addLayout(row)
        cl.addSpacing(6)
        t2 = QLabel("Color theme")
        t2.setObjectName("h2")
        cl.addWidget(t2)
        cl.addWidget(muted("Five color schemes, each in a dark and a light version."))
        srow = QHBoxLayout()
        srow.setSpacing(8)
        self.scheme_group = QButtonGroup(self)
        self.scheme_group.setExclusive(True)
        for key in palette.ORDER:
            sc = SchemeCard(key)
            sc.setChecked(s.scheme == key)
            sc.clicked.connect(lambda _c=False, k=key: self._set_scheme(k))
            self.scheme_group.addButton(sc)
            srow.addWidget(sc)
        srow.addStretch()
        cl.addLayout(srow)
        lay.addWidget(card)

        # startup
        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(12)
        t = QLabel("Startup & window")
        t.setObjectName("h2")
        cl.addWidget(t)
        self.sw_start = self._toggle_row(cl, "Open at login", s.start_at_login)
        self.sw_start.toggled.connect(self._on_start)
        self.sw_min = self._toggle_row(cl, "Start hidden in the menu bar", s.start_minimized)
        self.sw_min.toggled.connect(lambda on: self._set("start_minimized", on))
        self.sw_tray = self._toggle_row(cl, "Closing the window keeps the app running in the menu bar", s.close_to_tray)
        self.sw_tray.toggled.connect(lambda on: self._set("close_to_tray", on))
        lay.addWidget(card)

        # permissions
        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(10)
        t = QLabel("Permissions")
        t.setObjectName("h2")
        cl.addWidget(t)
        cl.addWidget(muted("macOS only lets FX Hotkeys see and send key presses after you allow it in "
                           "System Settings \u2192 Privacy & Security \u2192 Accessibility. "
                           "After an update you may have to remove FX Hotkeys there and add it again."))
        self.perm = QLabel()
        cl.addWidget(self.perm)
        row = QHBoxLayout()
        b = QPushButton("Ask for access")
        b.clicked.connect(lambda: macapi.is_trusted(prompt=True))
        row.addWidget(b)
        b = QPushButton("Open Accessibility settings")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(macapi.ACCESSIBILITY_URL)))
        row.addWidget(b)
        row.addStretch()
        cl.addLayout(row)
        lay.addWidget(card)
        self.refresh_permission()

        # backup
        card = make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(10)
        t = QLabel("Backup")
        t.setObjectName("h2")
        cl.addWidget(t)
        cl.addWidget(muted("Export your programs and shortcuts to a file, or load them on another Mac (or PC)."))
        row = QHBoxLayout()
        for text, slot in (("Export...", win.export_cfg), ("Import...", win.import_cfg),
                           ("Open data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(config.data_dir())))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        cl.addLayout(row)
        lay.addWidget(card)

        # about / credit
        about = QHBoxLayout()
        about.setSpacing(4)
        about.setContentsMargins(0, 0, 0, 0)
        about.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        by = muted(f"FX Hotkeys {__version__}  ·  made by ")
        by.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        about.addWidget(by, 0, Qt.AlignmentFlag.AlignVCenter)
        name = GradientText("a7yanan", 9.5)
        name.setClickable(True)
        name.setToolTip("https://x.com/3omara7yanan")
        name.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://x.com/3omara7yanan")))
        about.addWidget(name, 0, Qt.AlignmentFlag.AlignVCenter)
        about.addStretch()
        lay.addLayout(about)
        lay.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrolled(inner))

    def refresh_permission(self) -> None:
        ok, active = macapi.is_trusted(), self.win.engine.hook_active
        c = theme.colors()
        if ok and active:
            text, col = "\u25cf  Accessibility: allowed \u2014 shortcuts are working", c["ok"]
        elif ok:
            text, col = "\u25cf  Accessibility: allowed \u2014 starting the keyboard listener...", c["muted"]
        else:
            text, col = "\u25cf  Accessibility: not allowed \u2014 shortcuts can't work yet", c["danger"]
        self.perm.setText(text)
        self.perm.setStyleSheet(f"color: {col}; font-weight: 600;")

    @staticmethod
    def _toggle_row(layout, text: str, value: bool) -> Switch:
        row = QHBoxLayout()
        row.addWidget(QLabel(text))
        row.addStretch()
        sw = Switch(value)
        row.addWidget(sw)
        layout.addLayout(row)
        return sw

    def _set(self, key, on):
        setattr(self.win.cfg.settings, key, on)
        self.win.commit()

    def _set_theme(self, mode):
        self.win.cfg.settings.theme = mode
        theme.apply(QApplication.instance(), mode, self.win.cfg.settings.scheme)
        self.win.theme_changed()

    def _set_scheme(self, key):
        self.win.cfg.settings.scheme = key
        theme.apply(QApplication.instance(), self.win.cfg.settings.theme, key)
        self.win.theme_changed()

    def _on_start(self, on):
        try:
            macapi.set_startup(on)
        except Exception as e:      # noqa: BLE001
            QMessageBox.warning(self, "Startup", f"Could not change the login setting:\n{e}")
        self._set("start_at_login", on)


# ------------------------------------------------------------------ main window
class MainWindow(QMainWindow):
    def __init__(self, cfg, engine, server=None, server_name=""):
        super().__init__()
        self.cfg, self.engine = cfg, engine
        self.server, self.server_name = server, server_name
        self._quitting = False
        self.bridge = Bridge()
        self.bridge.log.connect(self._on_log)
        engine.on_log = self.bridge.log.emit
        self.setWindowTitle("FX Hotkeys")
        self.setWindowIcon(app_icon())
        self.resize(1140, 740)
        self.setMinimumSize(940, 620)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.flush)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.page_profile = ProfilePage(self)
        self.page_activity = ActivityPage()
        self.page_settings = SettingsPage(self)
        for pg in (self.page_profile, self.page_activity, self.page_settings):
            self.stack.addWidget(pg)
        h.addWidget(self.stack, 1)

        self._build_tray()
        self.fill_profiles(0)
        self._sync_pause_ui()

        # the keyboard listener starts by itself once Accessibility is allowed
        self._perm_timer = QTimer(self)
        self._perm_timer.timeout.connect(self._sync_pause_ui)
        self._perm_timer.start(2000)
        if macapi.HAVE_QUARTZ and not macapi.is_trusted():
            QTimer.singleShot(600, lambda: macapi.is_trusted(prompt=True))

    # ---- sidebar
    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(256)
        v = QVBoxLayout(side)
        v.setContentsMargins(16, 20, 16, 16)
        v.setSpacing(8)
        logo = QHBoxLayout()
        logo.setSpacing(10)
        pm = QLabel()
        pm.setPixmap(app_pixmap(36))
        logo.addWidget(pm)
        logo.addWidget(GradientText("FX Hotkeys", 15))
        logo.addStretch()
        v.addLayout(logo)
        v.addSpacing(16)
        lab = QLabel("PROGRAMS")
        lab.setObjectName("section")
        v.addWidget(lab)
        self.profile_list = QListWidget()
        self.profile_list.setObjectName("profiles")
        self.profile_list.setIconSize(QSize(26, 26))
        self.profile_list.currentRowChanged.connect(self._on_profile_row)
        self.profile_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.profile_list.customContextMenuRequested.connect(self._profile_context_menu)
        v.addWidget(self.profile_list, 1)
        add = QPushButton("+  Add program")
        add.setObjectName("primary")
        add.clicked.connect(self.add_profile)
        v.addWidget(add)
        v.addSpacing(6)
        self.nav_act = QPushButton("\u2630   Activity")
        self.nav_set = QPushButton("\u2699   Settings")
        for b, idx in ((self.nav_act, 1), (self.nav_set, 2)):
            b.setObjectName("ghost")
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, i=idx: self.show_page(i))
            v.addWidget(b)
        pill = QFrame()
        pill.setObjectName("pill")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(14, 8, 10, 8)
        self.status = QLabel()
        pl.addWidget(self.status)
        pl.addStretch()
        self.sw_pause = Switch(True)
        self.sw_pause.setToolTip("Turn all shortcuts on / off")
        self.sw_pause.toggled.connect(lambda on: self.set_paused(not on))
        pl.addWidget(self.sw_pause)
        v.addWidget(pill)
        return side

    def _profile_context_menu(self, pos) -> None:
        item = self.profile_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_del = menu.addAction("Remove program")
        act_del.triggered.connect(lambda: self._remove_profile_from_list(item))
        menu.exec(self.profile_list.mapToGlobal(pos))

    def _remove_profile_from_list(self, item: QListWidgetItem) -> None:
        pid = item.data(ROLE)
        p = next((x for x in self.cfg.profiles if x.id == pid), None)
        if p is not None:
            self.delete_profile(p)

    def resolve_running_icons(self) -> None:
        """Find .app paths for programs that are open right now (their icons)."""
        missing = [p for p in self.cfg.profiles
                   if p.exe.strip() and not (p.exe_path and os.path.exists(p.exe_path))]
        if not missing:
            return
        wins = macapi.list_windows_full()
        changed = False
        for p in missing:
            for exe, title, path in wins:
                if p.matches(exe, title):
                    p.exe_path, changed = path, True
                    break
        if changed:
            self.commit()

    def refresh_icons(self) -> None:
        for p in self.cfg.profiles:
            self.update_profile_item(p)
        self.page_profile.refresh_header_icon()

    def theme_changed(self) -> None:
        self._sync_pause_ui()
        self.refresh_icons()
        self.commit()

    def fill_profiles(self, select: int) -> None:
        self.resolve_running_icons()
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for p in self.cfg.profiles:
            it = QListWidgetItem()
            it.setData(ROLE, p.id)
            self.profile_list.addItem(it)
            self.update_profile_item(p, it)
        self.profile_list.blockSignals(False)
        if self.cfg.profiles:
            select = max(0, min(select, len(self.cfg.profiles) - 1))
            self.profile_list.setCurrentRow(select)
            self._on_profile_row(select)
        else:
            self.page_profile.set_profile(None)

    def update_profile_item(self, p: Profile, item: QListWidgetItem | None = None) -> None:
        if item is None:
            for i in range(self.profile_list.count()):
                if self.profile_list.item(i).data(ROLE) == p.id:
                    item = self.profile_list.item(i)
                    break
        if item:
            item.setText(p.name + ("" if p.enabled else "   (off)"))
            item.setIcon(QIcon(profile_icon(p, 26)))

    def _on_profile_row(self, row: int) -> None:
        if 0 <= row < len(self.cfg.profiles):
            self.page_profile.set_profile(self.cfg.profiles[row])
            self.show_page(0, keep_list=True)

    def show_page(self, idx: int, keep_list: bool = False) -> None:
        self.stack.setCurrentIndex(idx)
        self.nav_act.setChecked(idx == 1)
        self.nav_set.setChecked(idx == 2)
        if idx != 0 and not keep_list:
            self.profile_list.blockSignals(True)
            self.profile_list.setCurrentRow(-1)
            self.profile_list.blockSignals(False)
        elif idx == 0 and self.profile_list.currentRow() < 0 and self.cfg.profiles:
            self.profile_list.blockSignals(True)
            self.profile_list.setCurrentRow(0)
            self.profile_list.blockSignals(False)

    # ---- profiles
    def add_profile(self) -> None:
        p = Profile(name="New program")
        self.cfg.profiles.append(p)
        self.commit()
        self.fill_profiles(len(self.cfg.profiles) - 1)
        self.page_profile.tabs.setCurrentIndex(1)

    def delete_profile(self, p: Profile | None) -> None:
        if not p:
            return
        r = QMessageBox.question(self, "Delete program",
                                 f"Delete \u201c{p.name}\u201d and all of its shortcuts?")
        if r == QMessageBox.StandardButton.Yes:
            idx = self.cfg.profiles.index(p)
            self.cfg.profiles.remove(p)
            self.commit()
            self.fill_profiles(max(0, idx - 1))

    # ---- state
    def commit(self) -> None:
        self.engine.rebuild()
        self._save_timer.start(400)

    def flush(self) -> None:
        try:
            config.save(self.cfg)
        except OSError:
            pass

    def set_paused(self, paused: bool) -> None:
        self.engine.paused = paused
        self.cfg.settings.paused = paused
        self._sync_pause_ui()
        self.commit()

    def _sync_pause_ui(self) -> None:
        paused = self.engine.paused
        self.sw_pause.blockSignals(True)
        self.sw_pause.setChecked(not paused)
        self.sw_pause.blockSignals(False)
        c = theme.colors()
        if paused:
            text, col = "\u25cf  Paused", c["danger"]
        elif macapi.HAVE_QUARTZ and not self.engine.hook_active:
            text, col = "\u25cf  Needs permission", c["danger"]
        else:
            text, col = "\u25cf  Active", c["ok"]
        self.status.setText(text)
        self.status.setToolTip("Allow FX Hotkeys in System Settings \u2192 Privacy & Security \u2192 "
                               "Accessibility" if text.endswith("permission") else "")
        self.status.setStyleSheet(f"color: {col}; font-weight: 600;")
        if hasattr(self, "page_settings"):
            self.page_settings.refresh_permission()
        if hasattr(self, "act_pause"):
            self.act_pause.setText("Resume shortcuts" if paused else "Pause shortcuts")

    def _on_log(self, entry: dict) -> None:
        self.page_activity.add(entry)
        path = entry.get("path")
        if path and os.path.exists(path):             # first real use: learn the program's icon
            p = next((x for x in self.cfg.profiles if x.id == entry.get("profile_id")), None)
            if p and not (p.exe_path and os.path.exists(p.exe_path)):
                p.exe_path = path
                self.update_profile_item(p)
                if self.page_profile.p is p:
                    self.page_profile.refresh_header_icon()
                self.commit()

    # ---- backup
    def export_cfg(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export", "fxhotkeys-backup.json", "JSON (*.json)")
        if path:
            config.export_profiles(self.cfg, path)

    def import_cfg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON (*.json)")
        if not path:
            return
        try:
            profiles = config.import_profiles(path)
        except Exception as e:      # noqa: BLE001
            QMessageBox.warning(self, "Import", f"Could not read that file:\n{e}")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Import")
        box.setText(f"Found {len(profiles)} program(s). What should I do?")
        add = box.addButton("Add to my programs", QMessageBox.ButtonRole.AcceptRole)
        rep = box.addButton("Replace everything", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is rep:
            self.cfg.profiles = profiles
        elif box.clickedButton() is add:
            self.cfg.profiles.extend(profiles)
        else:
            return
        self.commit()
        self.fill_profiles(0)

    # ---- tray / lifecycle
    def _build_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(tray_icon(), self)
        self.tray.setToolTip("FX Hotkeys")
        menu = QMenu()
        open_a = QAction("Open FX Hotkeys", self)
        open_a.triggered.connect(self.show_window)
        self.act_pause = QAction("Pause shortcuts", self)
        self.act_pause.triggered.connect(lambda: self.set_paused(not self.engine.paused))
        quit_a = QAction("Quit", self)
        quit_a.triggered.connect(self.quit_app)
        menu.addAction(open_a)
        menu.addAction(self.act_pause)
        menu.addSeparator()
        menu.addAction(quit_a)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_click)
        self.tray.show()

    def _tray_click(self, reason) -> None:
        if sys.platform == "darwin":       # macOS shows the menu on click
            return
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.flush()
        QApplication.quit()

    def closeEvent(self, e) -> None:
        if self.cfg.settings.close_to_tray and self.tray and not self._quitting:
            e.ignore()
            self.hide()
            self.flush()
            return
        self._quitting = True
        self.flush()
        e.accept()
        QApplication.quit()
