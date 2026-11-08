"""Hotkey and macro-step helpers (pure Python: no macOS / Qt dependency).

Keys are identified by Windows-style virtual-key codes internally so configs
stay compatible with the Windows version; macapi.py maps them to macOS key codes.
The 4th modifier bit (WIN) is the Command key on macOS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CTRL, ALT, SHIFT, WIN = 1, 2, 4, 8
CMD = WIN
MOD_NAMES = {"ctrl": CTRL, "alt": ALT, "shift": SHIFT, "cmd": CMD}
MOD_ALIASES = {"control": "ctrl", "ctl": "ctrl", "\u2303": "ctrl",
               "option": "alt", "opt": "alt", "\u2325": "alt", "\u21e7": "shift",
               "command": "cmd", "\u2318": "cmd", "win": "cmd", "windows": "cmd",
               "meta": "cmd", "super": "cmd"}

_KEYS = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "pause": 0x13, "esc": 0x1B,
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "printscreen": 0x2C,
    "insert": 0x2D, "delete": 0x2E, "scrolllock": 0x91,
    "numpadclear": 0x0C, "numpadenter": 0x0E, "numpadequals": 0x92,
    "numpadmul": 0x6A, "numpadadd": 0x6B, "numpadsub": 0x6D,
    "numpaddot": 0x6E, "numpaddiv": 0x6F,
    "semicolon": 0xBA, "equals": 0xBB, "comma": 0xBC, "minus": 0xBD,
    "period": 0xBE, "slash": 0xBF, "backtick": 0xC0, "lbracket": 0xDB,
    "backslash": 0xDC, "rbracket": 0xDD, "quote": 0xDE,
}
for _i in range(26):
    _KEYS[chr(97 + _i)] = 0x41 + _i
for _i in range(10):
    _KEYS[str(_i)] = 0x30 + _i
    _KEYS[f"numpad{_i}"] = 0x60 + _i
for _i in range(1, 25):
    _KEYS[f"f{_i}"] = 0x6F + _i

KEY_ALIASES = {
    "escape": "esc", "return": "enter", "del": "delete", "ins": "insert",
    "pgup": "pageup", "pgdn": "pagedown", "spacebar": "space", "plus": "equals",
    "bksp": "backspace", "prtsc": "printscreen", "fwddelete": "delete",
    "forwarddelete": "delete", "help": "insert", "clear": "numpadclear",
    "-": "minus", ".": "period", ",": "comma", "/": "slash", ";": "semicolon",
    "=": "equals", "`": "backtick", "[": "lbracket", "]": "rbracket",
    "\\": "backslash", "'": "quote", "*": "numpadmul",
}
VK_TO_NAME = {v: k for k, v in _KEYS.items()}


def parse_hotkey(s: str):
    """'ctrl+numpad1' -> (mask, vk) or None when invalid."""
    if not s or not s.strip():
        return None
    mask, key = 0, None
    for tok in s.split("+"):
        t = tok.strip().lower()
        if not t:
            return None
        t = MOD_ALIASES.get(t, t)
        if t in MOD_NAMES:
            mask |= MOD_NAMES[t]
            continue
        if key is not None:
            return None
        t = KEY_ALIASES.get(t, t)
        if t in _KEYS:
            key = _KEYS[t]
        elif re.fullmatch(r"vk[0-9a-f]{2}", t):
            key = int(t[2:], 16)
        else:
            return None
    if key is None:
        return None
    return mask, key


def format_hotkey(mask: int, vk: int) -> str:
    parts = [n for n, m in (("ctrl", CTRL), ("alt", ALT), ("shift", SHIFT), ("cmd", CMD)) if mask & m]
    parts.append(VK_TO_NAME.get(vk, f"vk{vk:02x}"))
    return "+".join(parts)


_PRETTY = {"pageup": "Page Up", "pagedown": "Page Down", "printscreen": "Print Screen",
           "numpadmul": "Numpad *", "numpadadd": "Numpad +", "numpadsub": "Numpad -",
           "numpaddot": "Numpad .", "numpaddiv": "Numpad /", "numpadclear": "Numpad Clear",
           "numpadenter": "Numpad Enter", "numpadequals": "Numpad =",
           "backspace": "Delete \u232b", "delete": "Fwd Delete \u2326", "enter": "Return",
           "esc": "Esc", "insert": "Help", "semicolon": ";",
           "equals": "=", "comma": ",", "minus": "-", "period": ".", "slash": "/",
           "backtick": "`", "lbracket": "[", "rbracket": "]", "backslash": "\\", "quote": "'"}


def pretty_hotkey(s: str) -> str:
    p = parse_hotkey(s)
    if not p:
        return s or ""
    mask, vk = p
    # macOS order: Control, Option, Shift, Command
    out = [n for n, m in (("\u2303 Ctrl", CTRL), ("\u2325 Option", ALT), ("\u21e7 Shift", SHIFT),
                          ("\u2318 Cmd", CMD)) if mask & m]
    name = VK_TO_NAME.get(vk, f"VK {vk:02X}")
    if name.startswith("numpad") and len(name) == 7:
        out.append("Numpad " + name[6])
    elif name in _PRETTY:
        out.append(_PRETTY[name])
    elif len(name) == 1 or (name[0] == "f" and name[1:].isdigit()):
        out.append(name.upper())
    else:
        out.append(name.capitalize())
    return " + ".join(out)


# ------------------------------------------------------------------ steps
@dataclass
class Step:
    kind: str                                   # key | type | wait | click
    combos: list = field(default_factory=list)  # [(mask, vk), ...]
    text: str = ""
    ms: int = 0
    button: str = "left"
    count: int = 1


class StepError(ValueError):
    pass


_CMD_ALIASES = {"press": "key", "write": "type", "sleep": "wait", "pause": "wait"}


def parse_steps(text: str) -> list:
    steps = []
    for n, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cmd, _, rest = raw.lstrip().partition(" ")
        cmd = _CMD_ALIASES.get(cmd.lower(), cmd.lower())
        rest_s = rest.strip()
        if cmd == "key":
            if not rest_s:
                raise StepError(f"Line {n}: 'key' needs a key, e.g.  key ctrl+tab")
            combos = []
            for tok in rest_s.split():
                hk = parse_hotkey(tok)
                if not hk:
                    raise StepError(f"Line {n}: unknown key '{tok}'")
                combos.append(hk)
            steps.append(Step("key", combos=combos))
        elif cmd == "type":
            arg = rest.rstrip("\r\n")
            if arg == "":
                raise StepError(f"Line {n}: 'type' needs text, e.g.  type {{TEXT}}")
            steps.append(Step("type", text=arg))
        elif cmd == "wait":
            m = re.fullmatch(r"(\d+)\s*(ms)?", rest_s, re.I)
            if not m:
                raise StepError(f"Line {n}: 'wait' needs milliseconds, e.g.  wait 500")
            steps.append(Step("wait", ms=int(m.group(1))))
        elif cmd in ("click", "doubleclick"):
            b = rest_s.lower() or "left"
            if b not in ("left", "right", "middle"):
                raise StepError(f"Line {n}: click button must be left, right or middle")
            steps.append(Step("click", button=b, count=2 if cmd == "doubleclick" else 1))
        else:
            raise StepError(f"Line {n}: unknown command '{cmd}' (use key, type, wait, click)")
    return steps


def validate_steps(text: str):
    """-> (number_of_steps, error_or_None)"""
    try:
        return len(parse_steps(text)), None
    except StepError as e:
        return 0, str(e)


def fill_text(arg: str, text: str) -> str:
    return re.sub(r"\{text\}", lambda m: text, arg, flags=re.I)


def resolve_steps(text: str, clear_key: str = "ctrl+tab") -> str:
    """Replace {CLEAR} with the profile's clear-filters key before parsing."""
    key = (clear_key or "ctrl+tab").strip() or "ctrl+tab"
    return re.sub(r"\{CLEAR\}", key, text, flags=re.I)
