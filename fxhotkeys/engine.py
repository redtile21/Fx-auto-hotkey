"""Hotkey engine: decides when a shortcut fires and runs its steps.

No Qt in here on purpose - the UI listens through plain callbacks.
"""
from __future__ import annotations

import os
import threading
import time

from . import keys, macapi
from .config import AppConfig, Profile, Shortcut

_MOD_VK = {0xA0: keys.SHIFT, 0xA1: keys.SHIFT, 0xA2: keys.CTRL, 0xA3: keys.CTRL,
           0xA4: keys.ALT, 0xA5: keys.ALT, 0x5B: keys.WIN, 0x5C: keys.WIN,
           0x10: keys.SHIFT, 0x11: keys.CTRL, 0x12: keys.ALT}


class Engine:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.paused = cfg.settings.paused
        self.on_log = None                  # callable(dict)
        self._table = {}                    # (mask, vk) -> [(profile, shortcut)]
        self._mods = {}                     # physically held modifiers: vk -> mask
        self._swallowed = set()             # keys whose key-down we swallowed
        self._busy = threading.Lock()
        self._capture = None
        self._stop = threading.Event()
        self._hook = None
        self._due = {}                      # profile id -> (due_time, interval)
        self.rebuild()

    # ---------------------------------------------------------------- setup
    def set_config(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.rebuild()

    def rebuild(self) -> None:
        table = {}
        for p in self.cfg.profiles:
            if not p.enabled:
                continue
            for sc in p.shortcuts:
                if not sc.enabled:
                    continue
                hk = keys.parse_hotkey(sc.hotkey)
                if hk:
                    table.setdefault(hk, []).append((p, sc))
        self._table = table                 # atomic swap, read by the hook thread

    def start(self) -> None:
        self._stop.clear()
        self._hook = macapi.KeyboardHook(self._on_key)
        self._hook.start()
        threading.Thread(target=self._autosave_loop, daemon=True, name="autosave").start()

    @property
    def hook_active(self) -> bool:
        """False until macOS grants the Accessibility permission."""
        return bool(self._hook and self._hook.active)

    def stop(self) -> None:
        self._stop.set()
        if self._hook:
            self._hook.stop()

    # -------------------------------------------------------------- capture
    def start_capture(self, callback) -> None:
        """Next key combo is reported to callback(hotkey_string); '' = cancelled."""
        self._capture = callback

    def cancel_capture(self) -> None:
        self._capture = None

    # ------------------------------------------------------------ key hook
    def _mask(self) -> int:
        m = 0
        for v in self._mods.values():
            m |= v
        return m

    def _on_key(self, vk: int, down: bool) -> bool:
        mod = _MOD_VK.get(vk)
        if mod:
            if down:
                self._mods[vk] = mod
            else:
                self._mods.pop(vk, None)
            return False

        if not down:
            if vk in self._swallowed:
                self._swallowed.discard(vk)
                return True
            return False

        if vk in self._swallowed:           # auto-repeat of a swallowed key
            return True

        if not self._busy.locked():         # drop modifiers we missed the release of
            for k in list(self._mods):
                if not macapi.async_down(k):
                    self._mods.pop(k, None)

        mask = self._mask()
        cb = self._capture
        if cb is not None:
            self._swallowed.add(vk)
            self._capture = None
            if vk == 0x1B and mask == 0:
                cb("")
            else:
                cb(keys.format_hotkey(mask, vk))
            return True

        if self.paused:
            return False
        entries = self._table.get((mask, vk))
        if not entries:
            return False
        exe, title = macapi.foreground_info()
        hit = None
        for p, sc in sorted(entries, key=lambda e: e[0].is_global):
            if p.matches(exe, title):
                hit = (p, sc)
                break
        if not hit:
            return False

        self._swallowed.add(vk)
        if not self._busy.acquire(blocking=False):
            return True                     # a macro is already running
        threading.Thread(target=self._run, args=(hit[0], hit[1], True), daemon=True).start()
        return True

    # ------------------------------------------------------------- running
    def test_run(self, profile: Profile, sc: Shortcut, countdown: float = 3.0) -> None:
        def later():
            time.sleep(countdown)
            if self._busy.acquire(blocking=False):
                self._run(profile, sc, False)
        threading.Thread(target=later, daemon=True).start()

    def _run(self, profile: Profile, sc: Shortcut, release_mods: bool) -> None:
        """Runs one shortcut. The busy lock must already be held; released here."""
        error = ""
        held = list(self._mods) if release_mods else []
        try:
            raw = sc.steps.strip() or profile.steps
            steps = keys.parse_steps(keys.resolve_steps(raw, profile.clear_key))
            if held:
                macapi.release_modifiers(held)
            hkl = macapi.foreground_hkl()
            delay = max(0, profile.delay_ms) / 1000.0
            for i, st in enumerate(steps):
                self._exec(st, profile, sc, hkl)
                if i < len(steps) - 1:
                    time.sleep(delay)
        except Exception as e:                  # noqa: BLE001
            error = str(e) or e.__class__.__name__
        finally:
            still = [v for v in held if v in self._mods]
            if still:
                macapi.press_modifiers(still)
            self._busy.release()
        self._log(profile, sc, error)

    @staticmethod
    def _exec(st: keys.Step, profile: Profile, sc: Shortcut, hkl) -> None:
        if st.kind == "key":
            for j, (mask, vk) in enumerate(st.combos):
                if j:
                    time.sleep(0.02)
                macapi.tap(mask, vk)
        elif st.kind == "type":
            macapi.type_text(keys.fill_text(st.text, sc.text), profile.typing, hkl)
        elif st.kind == "wait":
            time.sleep(st.ms / 1000.0)
        elif st.kind == "click":
            macapi.click(st.button, st.count)

    def _log(self, profile, sc, error) -> None:
        if self.on_log:
            try:
                path = ""
                if not profile.exe_path or not os.path.exists(profile.exe_path):
                    path = macapi.foreground_path()      # lets the UI learn the program's icon
                self.on_log({"time": time.strftime("%H:%M:%S"), "profile": profile.name,
                             "profile_id": profile.id, "path": path,
                             "hotkey": sc.hotkey, "label": sc.text or sc.note, "error": error})
            except Exception:       # noqa: BLE001
                pass

    # ------------------------------------------------------------ autosave
    def _autosave_loop(self) -> None:
        while not self._stop.wait(1.0):
            if self.paused or self._busy.locked():
                continue
            now = time.monotonic()
            profiles = [p for p in list(self.cfg.profiles)
                        if p.enabled and p.autosave and not p.is_global]
            if not profiles:
                continue
            exe, title = macapi.foreground_info()
            for p in profiles:
                due, interval = self._due.get(p.id, (None, None))
                if due is None or interval != p.autosave_every:
                    self._due[p.id] = (now + p.autosave_every, p.autosave_every)
                    continue
                if now < due:
                    continue
                if not p.matches(exe, title):   # not in front right now: skip this round
                    self._due[p.id] = (now + p.autosave_every, p.autosave_every)
                    continue
                if self._mods:                  # user is holding a modifier: retry in a second
                    continue
                hk = keys.parse_hotkey(p.autosave_key)
                if not hk or not self._busy.acquire(blocking=False):
                    continue
                try:
                    macapi.tap(*hk)
                finally:
                    self._busy.release()
                self._due[p.id] = (now + p.autosave_every, p.autosave_every)
