# CLAUDE.md

FX Hotkeys for macOS: a PySide6 menu-bar app that sets keyboard shortcuts per app. A hotkey runs
a short macro (press keys, type text, wait, click), and the app can auto-save on a timer. It was
built to insert Bitwig Studio FX with one keystroke. It's a port of the Windows app
[a7yanan/Bitwig-FX-Hotkeys](https://github.com/a7yanan/Bitwig-FX-Hotkeys). Keep the credit to
a7yanan in the README and on the Settings page, as the original license asks for credit.

## Layout

| File | Role |
|---|---|
| `main.py` | Entry point: single instance (QLocalServer), theme, engine, window; `--tray` starts hidden |
| `fxhotkeys/macapi.py` | **The only macOS-specific module.** Quartz event tap (hook), CGEventPost (keys/text/clicks), NSWorkspace + Accessibility API (front app/window), LaunchAgent (open at login), permission checks |
| `fxhotkeys/engine.py` | Decides when a hotkey fires and runs its steps on a worker thread. No Qt. Talks to the OS only through `macapi` |
| `fxhotkeys/keys.py` | Pure Python: hotkey parsing/formatting, step parser (`key`/`type`/`wait`/`click`, `{TEXT}`, `{CLEAR}`) |
| `fxhotkeys/config.py` | Dataclasses (`AppConfig`/`Settings`/`Profile`/`Shortcut`) + JSON persistence, defaults (Bitwig profile) |
| `fxhotkeys/ui.py`, `widgets.py` | Qt main window, pages, dialogs, custom widgets |
| `fxhotkeys/theme.py`, `palette.py` | Qt style sheet, 5 color schemes × dark/light, font scaling |
| `tests/test_logic.py` | Plain-assert tests; fakes the `macapi` functions so they run on any OS |
| `build.sh` | venv → tests → PyInstaller `.app` → codesign (ad hoc, or `CODESIGN_ID`) → `.dmg` |
| `make_icon.py` | Regenerates `assets/icon.png`, `icon-1024.png`, `tray.png` (Pillow) |

## Key conventions

- **Keys are stored as Windows virtual-key codes** (`0x41` = A, `0x61` = Numpad 1, `0xA2` = left
  Ctrl…), so config files work with both the Windows and Mac versions. `macapi.VK_TO_MAC` /
  `MAC_TO_VK` translate to and from macOS key codes. When you add a key name in `keys._KEYS`, add
  its Mac key code in `macapi.py`. `test_mac_keycode_maps` checks that the mapping works both ways.
- **Modifier masks:** `CTRL=1, ALT=2, SHIFT=4, WIN=CMD=8`. The canonical names are
  `ctrl`/`alt`/`shift`/`cmd`. `win`, `meta`, `command`, `⌘`, `option`, `opt` are aliases.
- **App matching:** `Profile.exe` holds app names (the name shown in the menu bar, e.g.
  `Bitwig Studio`). `config._norm_exe` lowercases names and drops `.app`/`.exe` and non-letter/digit
  characters, so `bitwig-studio.exe` matches `Bitwig Studio`.
- **Every `macapi` function must degrade to a harmless stub** when not on macOS or when pyobjc is
  missing (`HAVE_QUARTZ`), so the engine, UI and tests import anywhere.
- `engine.py` never imports Qt. The UI gets updates through callbacks (`on_log`), which it bridges
  to Qt signals.
- Config format changes go through `from_dict` with defaults or migrations, e.g.
  `start_with_windows` → `start_at_login`. Never break old configs or Windows backups.

## macOS gotchas

- **Accessibility permission is required** for both the event tap and posting events.
  `KeyboardHook` keeps retrying until permission is granted. `engine.hook_active` reports whether
  it's running, and the UI shows "Needs permission" until it is.
- **The tap callback has to stay fast.** macOS turns off a tap that takes too long. The callback
  turns the tap back on, but avoid slow work in `Engine._on_key`. Accessibility queries have a
  0.25 s timeout (`_ax_app`).
- Events we post carry `kCGEventSourceUserData = _MAGIC`, so the tap ignores them, like the
  Windows hook's `LLKHF_INJECTED` check.
- Typed text always sets the Unicode string on the event. "keys" mode also sends the US key code.
- macOS links the Accessibility permission to the app's signature. With ad-hoc signing, each
  rebuild needs the permission granted again. A self-signed cert via `CODESIGN_ID` avoids that.
  The README explains it.
- Qt on macOS uses 72 dpi points, so sizes from the Windows design go through `theme.pt()`
  (×1.3 on macOS).

## Commands

```bash
python tests/test_logic.py              # tests; set FXHOTKEYS_HOME=$(mktemp -d) to keep your real config untouched
python main.py                          # run from source (needs requirements.txt; macOS for real hotkeys)
bash build.sh                           # build dist/FX Hotkeys.app + .dmg (macOS only)
CODESIGN_ID="FX Hotkeys Signing" bash build.sh   # same, signed with a stable identity
```

Config lives in `~/Library/Application Support/FXHotkeys/config.json` (or `$FXHOTKEYS_HOME/FXHotkeys/`),
with `error.log` next to it.

## Testing limits

The tests and an offscreen PySide6 smoke test (`QT_QPA_PLATFORM=offscreen`) run on Linux, but the
Quartz/AppKit code paths in `macapi.py` only run on a real Mac. If you change `macapi.py`, say
what still needs testing on macOS. The GitHub Actions workflow (`.github/workflows/build.yml`,
manual or `v*` tag) runs the tests on Ubuntu and builds an arm64 `.dmg` on `macos-14`.
