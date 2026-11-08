"""Thin pyobjc layer over the macOS Quartz / AppKit / Accessibility APIs.

The rest of the app talks in Windows-style virtual-key codes (see keys.py) so
configs stay portable; this module translates them to macOS key codes.

Everything here degrades to harmless stubs on other systems (or when pyobjc is
missing) so the rest of the app and the unit tests can be imported anywhere.
"""
from __future__ import annotations

import os
import plistlib
import sys
import threading
import time

IS_MAC = sys.platform == "darwin"

try:
    if not IS_MAC:
        raise ImportError
    import Quartz as Q
    from AppKit import NSWorkspace
    from ApplicationServices import (AXIsProcessTrusted, AXIsProcessTrustedWithOptions,
                                     AXUIElementCopyAttributeValue,
                                     AXUIElementCreateApplication,
                                     AXUIElementSetMessagingTimeout)
    from CoreFoundation import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource,
                                CFRunLoopGetCurrent, CFRunLoopRunInMode, CFRunLoopStop,
                                kCFRunLoopCommonModes, kCFRunLoopDefaultMode)
    HAVE_QUARTZ = True
except ImportError:                                     # not macOS / pyobjc missing
    HAVE_QUARTZ = False

# Marks events we post ourselves so the tap ignores them (like LLKHF_INJECTED).
_MAGIC = 0x46584854            # "FXHT"

# ------------------------------------------------------------ key code maps
# Windows VK  ->  macOS virtual key code (ANSI layout positions)
VK_TO_MAC = {}
for _ch, _kc in zip("asdfhgzxcv", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)):
    VK_TO_MAC[ord(_ch.upper())] = _kc
for _ch, _kc in (("b", 11), ("q", 12), ("w", 13), ("e", 14), ("r", 15), ("y", 16),
                 ("t", 17), ("o", 31), ("u", 32), ("i", 34), ("p", 35), ("l", 37),
                 ("j", 38), ("k", 40), ("n", 45), ("m", 46)):
    VK_TO_MAC[ord(_ch.upper())] = _kc
VK_TO_MAC.update({
    0x31: 18, 0x32: 19, 0x33: 20, 0x34: 21, 0x36: 22, 0x35: 23, 0x39: 25,
    0x37: 26, 0x38: 28, 0x30: 29,
    0xBB: 24, 0xBD: 27, 0xDD: 30, 0xDB: 33, 0xDE: 39, 0xBA: 41, 0xDC: 42,
    0xBC: 43, 0xBF: 44, 0xBE: 47, 0xC0: 50,
    0x0D: 36, 0x09: 48, 0x20: 49, 0x08: 51, 0x1B: 53, 0x2E: 117,
    0x24: 115, 0x23: 119, 0x21: 116, 0x22: 121, 0x2D: 114,
    0x25: 123, 0x27: 124, 0x28: 125, 0x26: 126, 0x0C: 71,
    # numpad
    0x60: 82, 0x61: 83, 0x62: 84, 0x63: 85, 0x64: 86, 0x65: 87, 0x66: 88,
    0x67: 89, 0x68: 91, 0x69: 92, 0x6E: 65, 0x6A: 67, 0x6B: 69, 0x6F: 75, 0x6D: 78,
    0x92: 81, 0x0E: 76,
    # function keys
    0x70: 122, 0x71: 120, 0x72: 99, 0x73: 118, 0x74: 96, 0x75: 97, 0x76: 98,
    0x77: 100, 0x78: 101, 0x79: 109, 0x7A: 103, 0x7B: 111, 0x7C: 105, 0x7D: 107,
    0x7E: 113, 0x7F: 106, 0x80: 64, 0x81: 79, 0x82: 80, 0x83: 90,
    # modifiers (left / right)
    0xA0: 56, 0xA1: 60, 0xA2: 59, 0xA3: 62, 0xA4: 58, 0xA5: 61, 0x5B: 55, 0x5C: 54,
    0x10: 56, 0x11: 59, 0x12: 58,
})
MAC_TO_VK = {}
for _vk, _kc in VK_TO_MAC.items():
    MAC_TO_VK.setdefault(_kc, _vk)
MAC_TO_VK.update({56: 0xA0, 59: 0xA2, 58: 0xA4})       # prefer the left-hand VKs

# modifier key code -> (device-dependent flag bit, generic flag mask)
_MOD_FLAGS = {
    56: (0x00000002, 0x00020000), 60: (0x00000004, 0x00020000),   # shift L / R
    59: (0x00000001, 0x00040000), 62: (0x00002000, 0x00040000),   # control L / R
    58: (0x00000020, 0x00080000), 61: (0x00000040, 0x00080000),   # option L / R
    55: (0x00000008, 0x00100000), 54: (0x00000010, 0x00100000),   # command L / R
}
_DEVICE_BITS = 0x0000207F
# keys.py masks (CTRL=1, ALT=2, SHIFT=4, WIN/CMD=8) -> Quartz flags
_MASK_TO_FLAGS = ((1, 0x00040000), (2, 0x00080000), (4, 0x00020000), (8, 0x00100000))
_MASK_TO_KEYCODE = ((1, 59), (2, 58), (4, 56), (8, 55))

# US layout: character -> (key code, needs shift). Used by "keys" typing mode.
_US = {}
for _a, _b, _kc in (("a", "A", 0), ("s", "S", 1), ("d", "D", 2), ("f", "F", 3), ("h", "H", 4),
                    ("g", "G", 5), ("z", "Z", 6), ("x", "X", 7), ("c", "C", 8), ("v", "V", 9),
                    ("b", "B", 11), ("q", "Q", 12), ("w", "W", 13), ("e", "E", 14), ("r", "R", 15),
                    ("y", "Y", 16), ("t", "T", 17), ("1", "!", 18), ("2", "@", 19), ("3", "#", 20),
                    ("4", "$", 21), ("6", "^", 22), ("5", "%", 23), ("=", "+", 24), ("9", "(", 25),
                    ("7", "&", 26), ("-", "_", 27), ("8", "*", 28), ("0", ")", 29), ("]", "}", 30),
                    ("o", "O", 31), ("u", "U", 32), ("[", "{", 33), ("i", "I", 34), ("p", "P", 35),
                    ("l", "L", 37), ("j", "J", 38), ("'", '"', 39), ("k", "K", 40), (";", ":", 41),
                    ("\\", "|", 42), (",", "<", 43), ("/", "?", 44), ("n", "N", 45), ("m", "M", 46),
                    (".", ">", 47), ("`", "~", 50)):
    _US[_a] = (_kc, False)
    _US[_b] = (_kc, True)
_US[" "] = (49, False)
_US["\t"] = (48, False)


def mac_keycode(vk: int):
    return VK_TO_MAC.get(vk)


def vk_from_mac(keycode: int):
    return MAC_TO_VK.get(keycode)


# ------------------------------------------------------------ permissions
def is_trusted(prompt: bool = False) -> bool:
    """True when this process has the Accessibility permission (needed to read
    and send keys). prompt=True shows macOS's 'grant access' dialog."""
    if not HAVE_QUARTZ:
        return False
    try:
        if prompt:
            return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}))
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


ACCESSIBILITY_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
INPUT_MONITORING_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"


# ------------------------------------------------------------ window info
def _ax(elem, attr):
    try:
        err, val = AXUIElementCopyAttributeValue(elem, attr, None)
        return val if err == 0 else None
    except Exception:
        return None


def _app_name(app) -> str:
    try:
        return str(app.localizedName() or "")
    except Exception:
        return ""


def _app_path(app) -> str:
    try:
        url = app.bundleURL() or app.executableURL()
        return str(url.path()) if url else ""
    except Exception:
        return ""


def _front_app():
    if not HAVE_QUARTZ:
        return None
    try:
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def _ax_app(pid: int):
    """AX element for an app, with a short timeout: this runs inside the event
    tap and macOS disables taps that take too long (e.g. on a hung app)."""
    elem = AXUIElementCreateApplication(pid)
    try:
        AXUIElementSetMessagingTimeout(elem, 0.25)
    except Exception:
        pass
    return elem


def _focused_title(pid: int) -> str:
    try:
        win = _ax(_ax_app(pid), "AXFocusedWindow")
        if win is None:
            return ""
        return str(_ax(win, "AXTitle") or "")
    except Exception:
        return ""


def foreground_path() -> str:
    """Bundle path of the active app ('' for our own windows)."""
    app = _front_app()
    if app is None or app.processIdentifier() == os.getpid():
        return ""
    return _app_path(app)


def foreground_info():
    """-> (app_name_lowercase, window_title) of the active window."""
    app = _front_app()
    if app is None:
        return "", ""
    return _app_name(app).lower(), _focused_title(app.processIdentifier())


def foreground_hkl():
    return None                     # keyboard layout handled by macOS itself


def list_windows_full():
    """Regular running apps and their windows -> [(app_name, title, bundle_path)]"""
    if not HAVE_QUARTZ:
        return []
    out, own = [], os.getpid()
    try:
        apps = NSWorkspace.sharedWorkspace().runningApplications()
    except Exception:
        return []
    for app in apps:
        try:
            if app.activationPolicy() != 0 or app.processIdentifier() == own:
                continue            # 0 = regular app with a Dock icon
            name, path = _app_name(app), _app_path(app)
            if not name:
                continue
            titles = []
            wins = _ax(_ax_app(app.processIdentifier()), "AXWindows") or []
            for w in wins:
                t = _ax(w, "AXTitle")
                if t:
                    titles.append(str(t))
            for t in titles or [""]:
                out.append((name, t, path))
        except Exception:
            continue
    return sorted(set(out), key=lambda t: (t[0].lower(), t[1].lower()))


def list_windows():
    return [(e, t) for e, t, _p in list_windows_full()]


def async_down(vk: int) -> bool:
    """Is the key physically held right now?"""
    if not HAVE_QUARTZ:
        return True
    kc = VK_TO_MAC.get(vk)
    if kc is None:
        return True
    try:
        return bool(Q.CGEventSourceKeyState(Q.kCGEventSourceStateHIDSystemState, kc))
    except Exception:
        return True


# ------------------------------------------------------------ sending input
_src = None


def _source():
    global _src
    if _src is None:
        _src = Q.CGEventSourceCreate(Q.kCGEventSourceStatePrivate)
    return _src


def _flags(mask: int) -> int:
    f = 0
    for bit, flag in _MASK_TO_FLAGS:
        if mask & bit:
            f |= flag
    return f


def _post(ev) -> None:
    Q.CGEventSetIntegerValueField(ev, Q.kCGEventSourceUserData, _MAGIC)
    Q.CGEventPost(Q.kCGHIDEventTap, ev)


def _key_event(keycode: int, down: bool, flags: int, text: str | None = None):
    ev = Q.CGEventCreateKeyboardEvent(_source(), keycode, down)
    Q.CGEventSetFlags(ev, flags)
    if text is not None:
        Q.CGEventKeyboardSetUnicodeString(ev, len(text.encode("utf-16-le")) // 2, text)
    return ev


def key_down(vk: int) -> None:
    kc = VK_TO_MAC.get(vk)
    if HAVE_QUARTZ and kc is not None:
        _post(_key_event(kc, True, 0))


def key_up(vk: int) -> None:
    kc = VK_TO_MAC.get(vk)
    if HAVE_QUARTZ and kc is not None:
        _post(_key_event(kc, False, 0))


def tap(mask: int, vk: int) -> None:
    """Press modifiers + key, then release everything."""
    if not HAVE_QUARTZ:
        return
    kc = VK_TO_MAC.get(vk)
    if kc is None:
        return
    flags, cur = _flags(mask), 0
    for bit, mkc in _MASK_TO_KEYCODE:                   # modifier downs
        if mask & bit:
            cur |= _flags(bit)
            _post(_key_event(mkc, True, cur))
    _post(_key_event(kc, True, flags))
    _post(_key_event(kc, False, flags))
    for bit, mkc in reversed(_MASK_TO_KEYCODE):         # modifier ups
        if mask & bit:
            cur &= ~_flags(bit)
            _post(_key_event(mkc, False, cur))


def release_modifiers(vks) -> None:
    """Tell apps the modifiers the user is physically holding are up, so the
    macro's keys are not combined with them."""
    if not HAVE_QUARTZ:
        return
    for vk in vks:
        kc = VK_TO_MAC.get(vk)
        if kc is not None:
            _post(_key_event(kc, False, 0))


def press_modifiers(vks) -> None:
    if not HAVE_QUARTZ:
        return
    flags = 0
    for vk in vks:
        kc = VK_TO_MAC.get(vk)
        if kc in _MOD_FLAGS:
            dev, gen = _MOD_FLAGS[kc]
            flags |= dev | gen
            _post(_key_event(kc, True, flags))


def type_text(text: str, mode: str = "keys", hkl=None) -> None:
    """Types text. Every event carries the character itself, so it is correct in
    any layout; in "keys" mode the matching US key code is sent along with it
    for apps that only look at key codes."""
    if not HAVE_QUARTZ:
        return
    for ch in text:
        if ch == "\r":
            continue
        if ch == "\n":
            tap(0, 0x0D)
        else:
            kc, shift = _US.get(ch, (0, False)) if mode == "keys" else (0, False)
            fl = 0x00020000 if shift else 0
            _post(_key_event(kc, True, fl, ch))
            _post(_key_event(kc, False, fl, ch))
        time.sleep(0.005)


def click(button: str = "left", count: int = 1) -> None:
    if not HAVE_QUARTZ:
        return
    down, up, btn = {"left": (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGMouseButtonLeft),
                     "right": (Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp, Q.kCGMouseButtonRight),
                     "middle": (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp, Q.kCGMouseButtonCenter),
                     }[button]
    pos = Q.CGEventGetLocation(Q.CGEventCreate(None))
    for n in range(1, count + 1):
        for typ in (down, up):
            ev = Q.CGEventCreateMouseEvent(_source(), typ, pos, btn)
            Q.CGEventSetIntegerValueField(ev, Q.kCGMouseEventClickState, n)
            _post(ev)
        time.sleep(0.03)


# ------------------------------------------------------------ keyboard hook
class KeyboardHook:
    """Quartz event tap running on its own thread.

    handler(vk, is_down) -> True to swallow the key, False to let it through.
    Events we posted ourselves are never passed to the handler.
    Needs the Accessibility permission; until it is granted the hook keeps
    retrying quietly, so granting it later works without a restart.
    """

    def __init__(self, handler):
        self._handler = handler
        self._tap = None
        self._loop = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.active = False

    def start(self) -> None:
        if not HAVE_QUARTZ:
            return
        threading.Thread(target=self._run, daemon=True, name="kbd-hook").start()
        self._ready.wait(2.0)

    def stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            try:
                CFRunLoopStop(self._loop)
            except Exception:
                pass

    def _callback(self, proxy, typ, event, refcon):
        try:
            if typ in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                if self._tap is not None:
                    Q.CGEventTapEnable(self._tap, True)
                return event
            if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData) == _MAGIC:
                return event
            kc = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
            vk = MAC_TO_VK.get(kc)
            if typ == Q.kCGEventFlagsChanged:
                if kc not in _MOD_FLAGS:
                    return event                        # caps lock, fn ...
                flags = Q.CGEventGetFlags(event)
                dev, gen = _MOD_FLAGS[kc]
                down = bool(flags & dev) if flags & _DEVICE_BITS else bool(flags & gen)
                vk = {56: 0xA0, 60: 0xA1, 59: 0xA2, 62: 0xA3,
                      58: 0xA4, 61: 0xA5, 55: 0x5B, 54: 0x5C}[kc]
                self._handler(vk, down)
                return event
            if vk is None:
                return event
            if self._handler(vk, typ == Q.kCGEventKeyDown):
                return None
        except Exception:
            pass
        return event

    def _create(self):
        mask = (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
                | Q.CGEventMaskBit(Q.kCGEventFlagsChanged))
        return Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                  Q.kCGEventTapOptionDefault, mask, self._callback, None)

    def _run(self) -> None:
        self._loop = CFRunLoopGetCurrent()
        self._tap = self._create()
        self._ready.set()
        while self._tap is None:                        # no permission yet: retry
            if self._stop.wait(2.0):
                return
            self._tap = self._create()
        src = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(self._loop, src, kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        self.active = True
        while not self._stop.is_set():
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 1.0, False)
        self.active = False
        Q.CGEventTapEnable(self._tap, False)


# ------------------------------------------------------------ system helpers
AGENT_LABEL = "com.fxhotkeys.mac"


def _agent_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", AGENT_LABEL + ".plist")


def _bundle_path():
    """/Applications/FX Hotkeys.app when running from a built app bundle."""
    exe = os.path.abspath(sys.executable)
    marker = ".app/Contents/MacOS/"
    i = exe.find(marker)
    return exe[:i + 4] if i >= 0 else None


def app_command() -> list:
    if getattr(sys, "frozen", False):
        bundle = _bundle_path()
        if bundle:
            return ["/usr/bin/open", "-a", bundle, "--args", "--tray"]
        return [sys.executable, "--tray"]
    return [sys.executable, os.path.abspath(sys.argv[0]), "--tray"]


def set_startup(enabled: bool, command: list | None = None) -> None:
    """Start at login via a per-user LaunchAgent."""
    path = _agent_path()
    if enabled:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            plistlib.dump({"Label": AGENT_LABEL, "ProgramArguments": command or app_command(),
                           "RunAtLoad": True, "ProcessType": "Interactive"}, f)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def is_startup() -> bool:
    return os.path.exists(_agent_path())
