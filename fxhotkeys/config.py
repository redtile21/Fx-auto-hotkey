"""Config model + JSON persistence."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict

from .palette import SCHEMES


DIR_NAME = "FXHotkeys"
# {CLEAR} is replaced at run-time by the profile's clear_key (default: ctrl+tab)
DEFAULT_STEPS = "key t\nkey b\ntype {TEXT}\nkey {CLEAR}\nkey down\nkey enter"


def data_dir() -> str:
    """~/Library/Application Support/FXHotkeys (override with FXHOTKEYS_HOME)."""
    base = os.environ.get("FXHOTKEYS_HOME") or os.path.join(
        os.path.expanduser("~"), "Library", "Application Support")
    d = os.path.join(base, DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def _id() -> str:
    return uuid.uuid4().hex[:8]


def _norm_exe(name: str) -> str:
    """'Bitwig Studio.app' / 'bitwig studio' / 'bitwig-studio.exe' -> 'bitwigstudio'
    (spaces, dashes etc. are ignored so Windows configs match Mac app names)."""
    n = name.strip().rstrip("/").lower()
    for ext in (".app", ".exe"):
        if n.endswith(ext):
            n = n[:-len(ext)]
    return "".join(ch for ch in n if ch.isalnum()) or n


@dataclass
class Shortcut:
    hotkey: str = ""
    text: str = ""
    note: str = ""
    steps: str = ""          # empty = use the program's default steps
    enabled: bool = True
    id: str = field(default_factory=_id)

    @staticmethod
    def from_dict(d: dict) -> "Shortcut":
        return Shortcut(
            hotkey=str(d.get("hotkey", "")), text=str(d.get("text", "")),
            note=str(d.get("note", "")), steps=str(d.get("steps", "")),
            enabled=bool(d.get("enabled", True)), id=str(d.get("id") or _id()))


@dataclass
class Profile:
    name: str = "New program"
    exe: str = ""            # app name(s), comma separated, e.g. "Bitwig Studio"
    title: str = ""          # window title contains
    exe_path: str = ""       # path of the .app bundle (used for its icon)
    enabled: bool = True
    delay_ms: int = 250
    typing: str = "keys"     # keys | unicode
    steps: str = DEFAULT_STEPS
    clear_key: str = "ctrl+tab"   # key used where {CLEAR} appears in steps
    autosave: bool = False
    autosave_every: int = 60
    autosave_key: str = "cmd+s"
    shortcuts: list = field(default_factory=list)
    id: str = field(default_factory=_id)

    @property
    def is_global(self) -> bool:
        return not self.exe.strip() and not self.title.strip()

    def matches(self, exe: str, title: str) -> bool:
        exes = [_norm_exe(e) for e in self.exe.split(",") if e.strip()]
        t = self.title.strip().lower()
        if exes and _norm_exe(exe) not in exes:
            return False
        if t and t not in (title or "").lower():
            return False
        return True

    def describe(self) -> str:
        if self.is_global:
            return "All programs"
        parts = []
        if self.exe.strip():
            parts.append(self.exe.strip())
        if self.title.strip():
            parts.append(f"title contains \u201c{self.title.strip()}\u201d")
        return "  \u00b7  ".join(parts)

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        def _int(v, default, lo, hi):
            try:
                return max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                return default
        return Profile(
            name=str(d.get("name", "Program")) or "Program",
            exe=str(d.get("exe", "")), title=str(d.get("title", "")),
            exe_path=str(d.get("exe_path", "")),
            enabled=bool(d.get("enabled", True)),
            delay_ms=_int(d.get("delay_ms", 250), 250, 0, 10000),
            typing=d.get("typing") if d.get("typing") in ("keys", "unicode") else "keys",
            steps=str(d.get("steps", DEFAULT_STEPS)),
            clear_key=str(d.get("clear_key", "ctrl+tab")) or "ctrl+tab",
            autosave=bool(d.get("autosave", False)),
            autosave_every=_int(d.get("autosave_every", 60), 60, 5, 86400),
            autosave_key=str(d.get("autosave_key", "cmd+s")) or "cmd+s",
            shortcuts=[Shortcut.from_dict(s) for s in d.get("shortcuts", []) if isinstance(s, dict)],
            id=str(d.get("id") or _id()))


@dataclass
class Settings:
    theme: str = "dark"                 # dark | light | system
    scheme: str = "aurora"              # aurora | citrus | mono | crimson | neon
    start_at_login: bool = False
    start_minimized: bool = False
    close_to_tray: bool = True
    paused: bool = False

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        s = Settings()
        for k in ("start_at_login", "start_minimized", "close_to_tray", "paused"):
            if k in d:
                setattr(s, k, bool(d[k]))
        if "start_at_login" not in d and "start_with_windows" in d:   # Windows backup
            s.start_at_login = bool(d["start_with_windows"])
        if d.get("theme") in ("dark", "light", "system"):
            s.theme = d["theme"]
        if d.get("scheme") in SCHEMES:
            s.scheme = d["scheme"]
        return s


@dataclass
class AppConfig:
    settings: Settings = field(default_factory=Settings)
    profiles: list = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AppConfig":
        return AppConfig(
            settings=Settings.from_dict(d.get("settings", {})),
            profiles=[Profile.from_dict(p) for p in d.get("profiles", []) if isinstance(p, dict)])


# ------------------------------------------------------------ defaults
def default_config() -> AppConfig:
    """The shortcuts of the original FX.ahk script, for Bitwig Studio on macOS."""
    bitwig = Profile(name="Bitwig Studio", exe="Bitwig Studio", autosave=True)
    app = "/Applications/Bitwig Studio.app"
    if os.path.isdir(app):
        bitwig.exe_path = app
    eq_plus = "key t\nkey b\nkey alt+c\ntype {TEXT}\nkey {CLEAR}\nkey down\nclick\nkey enter"
    comp = "key t\nkey b\ntype {TEXT}\nkey {CLEAR}\nkey down\nwait 250\nkey enter"
    items = [
        ("ctrl+numpad1", "EQ+", eq_plus), ("ctrl+numpad2", "eq2", ""),
        ("ctrl+numpad3", "Freq Split", ""), ("ctrl+numpad4", "pro-q 4", ""),
        ("ctrl+numpad5", "eq 5", ""), ("ctrl+numpad6", "Chain", ""),
        ("ctrl+numpad7", "Compressor+", comp), ("ctrl+numpad8", "Convolution", ""),
        ("ctrl+numpad9", "Over", ""),
        ("ctrl+1", "tool", ""), ("ctrl+2", "soothe2", ""),
        ("ctrl+3", "transient control", ""), ("ctrl+4", "neutron 5 exciter", ""),
        ("ctrl+5", "filter", ""), ("ctrl+6", "oscill", ""), ("ctrl+7", "chorus+", ""),
        ("ctrl+8", "stereo split", ""), ("ctrl+9", "time shift", ""),
        ("ctrl+0", "ozone 12 max", ""),
    ]
    bitwig.shortcuts = [Shortcut(hotkey=h, text=t, steps=s) for h, t, s in items]
    return AppConfig(profiles=[bitwig])


# ------------------------------------------------------------ persistence
def save(cfg: AppConfig, path: str | None = None) -> None:
    path = path or config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load(path: str | None = None) -> AppConfig:
    path = path or config_path()
    if not os.path.exists(path):
        cfg = default_config()
        save(cfg, path)
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            return AppConfig.from_dict(json.load(f))
    except Exception:
        try:
            os.replace(path, path + ".bak")
        except OSError:
            pass
        cfg = default_config()
        save(cfg, path)
        return cfg


def export_profiles(cfg: AppConfig, path: str) -> None:
    save(cfg, path)


def import_profiles(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    profiles = [Profile.from_dict(p) for p in data.get("profiles", []) if isinstance(p, dict)]
    for p in profiles:          # fresh ids so imported items never clash
        p.id = _id()
        for s in p.shortcuts:
            s.id = _id()
    return profiles
