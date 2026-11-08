# FX Hotkeys for macOS

A macOS version of [**Bitwig FX Hotkeys**](https://github.com/a7yanan/Bitwig-FX-Hotkeys) by
[a7yanan](https://x.com/3omara7yanan). It's a Mac app with a modern UI for **per-app keyboard
shortcuts**, typed-text macros and auto-save. It was built for adding FX to Bitwig Studio with
one keystroke.

Press a hotkey in Bitwig and FX Hotkeys opens the browser, types the device name (e.g. `EQ+`),
clears the filters and inserts the first result.

---

## Features

- Separate hotkeys for each app, or global hotkeys for all apps
- Steps you can customize: `key` · `type {TEXT}` · `wait` · `click`
- A **Clear filters** key for each app (`{CLEAR}` in steps)
- Auto-save: presses ⌘S every N seconds while the app is in front
- 5 color themes, each in a dark and a light version (or follow the system)
- Menu-bar icon, optional **Open at login**
- Export / import settings. Backups from the Windows version also import.

---

## Install

1. Download `FXHotkeys-macOS-arm64.dmg` (see **Build** below), open it and drag **FX Hotkeys**
   into **Applications**.
2. The app isn't notarized, so the first time you open it, **right-click → Open** in Finder and
   confirm.
3. **Grant Accessibility access.** macOS asks for it on first launch. You can also go to
   **System Settings → Privacy & Security → Accessibility** and turn **FX Hotkeys** on.
   FX Hotkeys can't see or send key presses without this permission. The sidebar shows
   **● Needs permission** until access is granted, then switches to **● Active** by itself
   without a restart.

> After installing a new build, macOS may keep the old permission entry and ignore the new app.
> If shortcuts stop working, remove FX Hotkeys from the Accessibility list (–) and add it again.

---

## Build

### With GitHub Actions (no local setup)

Open the **Actions** tab, then **Build macOS app** → **Run workflow**. When it finishes, download
**Artifacts → FXHotkeys-macOS-arm64** (Apple Silicon). For an Intel Mac, build on that Mac
locally.

### On your Mac

```bash
./build.sh
```

You need Python 3.10 or newer (from python.org or Homebrew). The script makes a virtualenv, runs
the tests, builds `dist/FX Hotkeys.app` with PyInstaller, signs it ad hoc and packs
`dist/FXHotkeys-macOS.dmg`. To sign with your own certificate, run
`CODESIGN_ID="Developer ID Application: …" ./build.sh`.

### Run from source

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

When you run from source, macOS asks for Accessibility access for the app that launched Python
(Terminal, iTerm, VS Code…). Grant it to that app.

---

## Bitwig Studio setup

The default profile matches the app named **Bitwig Studio**, so Bitwig must be in front for the
shortcuts to fire. It comes with the shortcuts from the original script:

| Hotkey | Inserts |
|---|---|
| ⌃ Ctrl + Numpad 1–9 | EQ+, eq2, Freq Split, pro-q 4, eq 5, Chain, Compressor+, Convolution, Over |
| ⌃ Ctrl + 1–0 | tool, soothe2, transient control, neutron 5 exciter, filter, oscill, chorus+, stereo split, time shift, ozone 12 max |

Things that work differently on a Mac:

- **Bitwig shortcuts.** The default steps (`key t`, `key b`, `key alt+c`, clear key `ctrl+tab`)
  come from the Windows setup. Bitwig on macOS uses **⌘ Cmd** where Windows uses Ctrl for many
  shortcuts. If a step does nothing, check the key in Bitwig's
  *Settings → Shortcuts* and change it in FX Hotkeys. Use the **Clear filters key** on the
  *Program* tab, or edit the steps directly, e.g. `key cmd+tab`.
- **⌃ Ctrl + number** switches Spaces/desktops if *Keyboard → Keyboard Shortcuts → Mission
  Control* has those shortcuts turned on. Turn them off there or pick other hotkeys.
- **No numpad?** Most MacBooks don't have one. Click a hotkey and press a new combo, e.g.
  ⌃⌥1 or ⌘⇧E.
- System shortcuts like ⌘Tab, ⌘Space and ⌘Q go to macOS first and can't be used as hotkeys.

---

## Steps

```
key t
key b
type {TEXT}
key {CLEAR}
key down
key enter
```

- `key <combo> [<combo> …]`: press keys, e.g. `key cmd+shift+s`, `key down down enter`
- `type <text>`: type text. `{TEXT}` is the shortcut's text field
- `wait <ms>`: pause
- `click [left|right|middle]` / `doubleclick`: click at the mouse position
- `{CLEAR}` is replaced by the app's clear-filters key (default `ctrl+tab`)
- Lines that start with `#` are comments

Modifier names: `ctrl` (⌃), `alt` / `option` / `opt` (⌥), `shift` (⇧), `cmd` / `command` (⌘).
`win` from Windows configs means ⌘.
Mac key names: `enter`/`return`, `backspace` (the ⌫ *delete* key), `delete`/`fwddelete` (⌦),
`esc`, `tab`, `space`, arrows, `home`, `end`, `pageup`, `pagedown`, `f1`–`f20`, `numpad0`–`numpad9`,
`numpadenter`, `numpadequals`, `numpadclear`, `numpadadd`, `numpadsub`, `numpadmul`, `numpaddiv`,
`numpaddot`.

**Typing mode:** each typed character carries the actual Unicode text, so it works with any
keyboard layout or language. *Keys* mode also sends the matching US key code, for apps that only
read key codes. *Unicode* mode sends only the character.

---

## Notes

- Settings: `~/Library/Application Support/FXHotkeys/config.json`. Errors are logged to
  `error.log` in the same folder.
- "Open at login" installs `~/Library/LaunchAgents/com.fxhotkeys.mac.plist`.
- Matching: **App name** is the name shown in the menu bar / Activity Monitor, e.g.
  `Bitwig Studio`. You can list several, separated by commas. **Window title contains** is
  optional and needs the Accessibility permission.

### How the port works

The UI, config, macro engine and themes come from the original project. The Windows layer
(`winapi.py`: low-level keyboard hook, `SendInput`, registry autostart, admin elevation) is
replaced by `fxhotkeys/macapi.py`, which uses:

- a Quartz **CGEventTap** to catch and swallow hotkeys,
- **CGEventPost** to send keys, text and clicks,
- **NSWorkspace** and the **Accessibility API** to find the app and window in front,
- a **LaunchAgent** for opening at login.

Keys are still stored as Windows-style virtual-key codes, so config files work on both versions.

---

## License / credit

Based on [a7yanan/Bitwig-FX-Hotkeys](https://github.com/a7yanan/Bitwig-FX-Hotkeys) (*"Free for
personal use. If you redistribute or modify it, please credit the original project."*). All
credit for the original design and app goes to a7yanan.
