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

## Install (recommended: build it on your Mac)

Building the app yourself takes about 5 minutes. You don't need an Apple developer account, and
macOS opens the app without any "unidentified developer" warning, because only downloaded apps
get checked.

1. **Install Python 3.10 or newer** from [python.org](https://www.python.org/downloads/macos/) and
   run its installer. (`brew install python` works too.)
2. **Get the code:** on this repo's GitHub page, click **Code → Download ZIP** and double-click
   the ZIP to unpack it. (Or `git clone` it.)
3. **Build:** open **Terminal**, type `cd ` (with a space), drag the unpacked folder onto the
   Terminal window, press Return, then run:

   ```bash
   bash build.sh
   ```

   The script installs everything it needs into a local `.venv` folder, runs the tests and
   creates `dist/FX Hotkeys.app` and `dist/FXHotkeys-macOS.dmg`.
4. **Install:** drag `dist/FX Hotkeys.app` into **Applications** and open it.
5. **Grant Accessibility access:** macOS asks on first launch. Turn on **FX Hotkeys** in
   **System Settings → Privacy & Security → Accessibility**. FX Hotkeys can't see or send key
   presses without this permission. The sidebar shows **● Needs permission** until access is
   granted, then switches to **● Active** by itself without a restart.

### Rebuilding later (optional: keep the permission)

macOS links the Accessibility permission to the app's signature. By default every build gets a
new signature, so after a rebuild the shortcuts stop working until you remove **FX Hotkeys** from
the Accessibility list (**–**) and add it again (**+**).

To avoid that, make a free signing certificate once:

1. Open **Keychain Access**, then in the menu bar choose **Keychain Access → Certificate Assistant →
   Create a Certificate…**
2. Name: `FX Hotkeys Signing`. Identity Type: **Self Signed Root**. Certificate Type:
   **Code Signing**. Click **Create**.
3. Build with it:

   ```bash
   CODESIGN_ID="FX Hotkeys Signing" bash build.sh
   ```

   If macOS asks whether `codesign` may use the key, click **Always Allow**.

Builds signed this way keep the same identity, so the permission stays granted after a rebuild.
Grant it once more after the first build signed with the new certificate.

### Other ways to run it

**Download a ready-made build (Apple Silicon only).** In this repo's **Actions** tab, run
**Build macOS app** and download **Artifacts → FXHotkeys-macOS-arm64**. The app isn't notarized
by Apple, so macOS blocks downloaded copies the first time. To allow it, do one of these:

- Try to open the app, click **Done**, then go to **System Settings → Privacy & Security** and
  click **Open Anyway**. On macOS 14 and earlier you can right-click the app and choose **Open**
  instead.
- Or remove the download mark in Terminal:

  ```bash
  xattr -dr com.apple.quarantine "/Applications/FX Hotkeys.app"
  ```

**Run from source (no app, no signing).**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

macOS asks for Accessibility access for the app that runs Python (Terminal, iTerm, VS Code…).
Grant it to that app. Shortcuts only work while that Terminal window keeps running.

**Notarized builds for sharing.** If you want to give the app to other people without any
warnings, you need a paid Apple Developer account. Build with your
`CODESIGN_ID="Developer ID Application: …"` and then notarize the `.dmg` with `xcrun notarytool`.

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
