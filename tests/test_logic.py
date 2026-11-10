import os, sys, time, tempfile, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fxhotkeys import keys, config, macapi, engine as eng
winapi = macapi   # the engine's OS layer (patched with fakes below)

# ---------- config round trip
def test_config_roundtrip():
    d = tempfile.mkdtemp(); path = os.path.join(d, "c.json")
    cfg = config.load(path)
    assert len(cfg.profiles) == 1 and len(cfg.profiles[0].shortcuts) == 19
    cfg.profiles[0].shortcuts[0].text = "\u0645\u0631\u062d\u0628\u0627"
    config.save(cfg, path)
    cfg2 = config.load(path)
    assert cfg2.profiles[0].shortcuts[0].text == "\u0645\u0631\u062d\u0628\u0627"
    open(path, "w").write("{broken")
    assert len(config.load(path).profiles) == 1 and os.path.exists(path + ".bak")

def test_default_steps_parse_and_hotkeys_valid():
    cfg = config.default_config()
    for p in cfg.profiles:
        assert keys.validate_steps(keys.resolve_steps(p.steps, p.clear_key))[1] is None
        for s in p.shortcuts:
            assert keys.parse_hotkey(s.hotkey), s.hotkey
            if s.steps: assert keys.validate_steps(keys.resolve_steps(s.steps, p.clear_key))[1] is None

def test_profile_matching():
    p = config.Profile(exe="Bitwig Studio.app, other", title="")
    assert p.matches("bitwig studio", "x") and p.matches("OTHER", "") and not p.matches("textedit", "")
    assert config.Profile(exe="bitwig-studio.exe").matches("bitwig studio", "")   # Windows backup
    q = config.Profile(title="Bitwig Studio")
    assert q.matches("anything", "My Song - bitwig studio 5") and not q.matches("a", "Notes")
    assert config.Profile().is_global and not q.is_global

# ---------- engine with a fake macOS
class Fake:
    def __init__(self):
        self.calls = []; self.fg = ("bitwig studio", "Bitwig Studio - x")
        winapi.foreground_info = lambda: self.fg
        winapi.foreground_hkl = lambda: None
        winapi.async_down = lambda vk: True
        winapi.tap = lambda m, v: self.calls.append(("tap", m, v))
        winapi.type_text = lambda t, mode, hkl: self.calls.append(("type", t, mode))
        winapi.click = lambda b, c: self.calls.append(("click", b, c))
        winapi.release_modifiers = lambda v: self.calls.append(("release", tuple(v)))
        winapi.press_modifiers = lambda v: self.calls.append(("press", tuple(v)))

def wait_idle(e):
    for _ in range(200):
        if not e._busy.locked(): return
        time.sleep(0.01)
    raise AssertionError("still busy")

def test_hotkey_fires_and_runs_steps():
    f = Fake(); cfg = config.default_config()
    for p in cfg.profiles: p.delay_ms = 0
    e = eng.Engine(cfg); logs = []; e.on_log = logs.append
    assert e._on_key(0xA2, True) is False                 # Ctrl down
    assert e._on_key(0x61, True) is True                  # Numpad1 -> swallowed
    wait_idle(e); time.sleep(0.05)
    kinds = [c[0] for c in f.calls]
    assert f.calls[0] == ("release", (0xA2,))
    assert ("tap", 2, 0x43) in f.calls                    # alt+c  (custom steps for ctrl+numpad1)
    assert ("type", "EQ+", "keys") in f.calls and ("click", "left", 1) in f.calls
    assert f.calls[-1] == ("press", (0xA2,))              # ctrl restored (still held)
    assert logs and logs[0]["error"] == "" and logs[0]["label"] == "EQ+"
    assert e._on_key(0x61, True) is True                  # auto-repeat swallowed, not re-run
    assert e._on_key(0x61, False) is True                 # key-up swallowed
    assert e._on_key(0xA2, False) is False

def test_wrong_window_passes_through():
    f = Fake(); f.fg = ("textedit", "Untitled")
    e = eng.Engine(config.default_config())
    e._on_key(0xA2, True)
    assert e._on_key(0x31, True) is False and f.calls == []

def test_global_profile_and_priority():
    f = Fake(); f.fg = ("anything", "x")
    cfg = config.AppConfig(profiles=[
        config.Profile(name="All", delay_ms=0, steps="type G", shortcuts=[config.Shortcut(hotkey="f9", text="all")]),
        config.Profile(name="Any", exe="Anything", delay_ms=0, steps="type S", shortcuts=[config.Shortcut(hotkey="f9", text="spec")])])
    e = eng.Engine(cfg)
    assert e._on_key(0x78, True) is True; wait_idle(e); time.sleep(0.05)
    assert ("type", "S", "keys") in f.calls and ("type", "G", "keys") not in f.calls

def test_disabled_and_pause():
    f = Fake()
    cfg = config.default_config(); cfg.profiles[0].shortcuts[1].enabled = False
    e = eng.Engine(cfg)
    e._on_key(0xA2, True)
    assert e._on_key(0x62, True) is False                 # ctrl+numpad2 disabled
    e.paused = True
    assert e._on_key(0x63, True) is False                 # paused -> pass through

def test_capture():
    f = Fake(); e = eng.Engine(config.default_config()); got = []
    e.start_capture(got.append)
    e._on_key(0xA2, True); e._on_key(0xA0, True)
    assert e._on_key(0x61, True) is True
    assert got == ["ctrl+shift+numpad1"]
    assert e._on_key(0x61, True) is True and e._on_key(0x61, False) is True   # no re-trigger
    e.start_capture(got.append); e._on_key(0xA2, False); e._on_key(0xA0, False)
    assert e._on_key(0x1B, True) is True and got[-1] == ""

def test_bad_steps_logged_not_crash():
    f = Fake()
    cfg = config.AppConfig(profiles=[config.Profile(name="X", title="", steps="bogus", shortcuts=[config.Shortcut(hotkey="f8", text="t")])])
    e = eng.Engine(cfg); logs = []; e.on_log = logs.append
    assert e._on_key(0x77, True) is True; wait_idle(e); time.sleep(0.05)
    assert "unknown command" in logs[0]["error"] and not e._busy.locked()

def test_autosave_loop_sends_when_active():
    f = Fake()
    cfg = config.AppConfig(profiles=[config.Profile(name="B", title="Bitwig", autosave=True, autosave_every=5)])
    e = eng.Engine(cfg)
    orig_wait = e._stop.wait
    ticks = {"n": 0}
    base = time.monotonic()
    import fxhotkeys.engine as m
    clock = {"t": base}
    m.time = type("T", (), {"monotonic": staticmethod(lambda: clock["t"]), "sleep": time.sleep, "strftime": time.strftime})
    def fake_wait(_):
        ticks["n"] += 1; clock["t"] += 3
        return ticks["n"] > 6
    e._stop.wait = fake_wait
    e._autosave_loop()
    assert f.calls.count(("tap", keys.CMD, 0x53)) >= 1, f.calls       # cmd+s

def test_schemes_and_contrast():
    from fxhotkeys import palette as P
    assert len(P.ORDER) == 5 and set(P.ORDER) == set(P.SCHEMES)
    for sch in P.ORDER:
        for mode in ("dark", "light"):
            c = P.build(mode, sch)
            assert P.contrast(c["text"], c["bg"]) >= 4.5 and P.contrast(c["text"], c["surface"]) >= 4.5
            assert P.contrast(c["muted"], c["surface"]) >= 3.0
            assert P.contrast(c["on_accent"], c["grad_a"]) >= 2.3 and P.contrast(c["on_accent"], c["grad_b"]) >= 2.3
    assert P.build("dark", "nope")["grad_a"] == P.build("dark", "aurora")["grad_a"]   # unknown -> default

def test_scheme_and_exe_path_persist():
    d = tempfile.mkdtemp(); path = os.path.join(d, "c.json")
    cfg = config.load(path)
    cfg.settings.scheme = "citrus"; cfg.profiles[0].exe_path = "/Applications/Bitwig Studio.app"
    config.save(cfg, path)
    c2 = config.load(path)
    assert c2.settings.scheme == "citrus" and c2.profiles[0].exe_path.endswith("Bitwig Studio.app")
    import json
    data = json.load(open(path)); data["settings"]["scheme"] = "bogus"
    json.dump(data, open(path, "w")); assert config.load(path).settings.scheme == "aurora"

def test_log_reports_profile_id_and_path():
    f = Fake(); winapi.foreground_path = lambda: "/bin/ls"
    cfg = config.default_config()
    for p in cfg.profiles: p.delay_ms = 0; p.exe_path = ""
    e = eng.Engine(cfg); logs = []; e.on_log = logs.append
    e._on_key(0xA2, True); e._on_key(0x62, True); wait_idle(e); time.sleep(0.05)
    assert logs[0]["profile_id"] == cfg.profiles[0].id and logs[0]["path"] == "/bin/ls"

# ---------- macOS specifics
def test_cmd_modifier_names():
    assert keys.parse_hotkey("cmd+s") == (keys.CMD, 0x53)
    for alias in ("command+s", "\u2318+s", "win+s", "meta+s"):
        assert keys.parse_hotkey(alias) == (keys.CMD, 0x53), alias
    assert keys.parse_hotkey("option+c") == keys.parse_hotkey("alt+c") == (keys.ALT, 0x43)
    assert keys.format_hotkey(keys.CMD | keys.SHIFT, 0x53) == "shift+cmd+s"
    assert keys.pretty_hotkey("cmd+ctrl+numpad1") == "\u2303 Ctrl + \u2318 Cmd + Numpad 1"
    assert keys.parse_hotkey("numpadenter") and keys.parse_hotkey("fwddelete") == (0, 0x2E)

def test_mac_keycode_maps():
    # every named key that has a Mac key code round-trips VK -> mac -> VK
    for name, vk in keys._KEYS.items():
        kc = macapi.mac_keycode(vk)
        if kc is None:
            continue
        assert macapi.vk_from_mac(kc) == vk, (name, vk, kc)
    m = macapi.mac_keycode
    assert (m(0x41), m(0x53), m(0x0D), m(0x09), m(0x1B), m(0x08)) == (0, 1, 36, 48, 53, 51)
    assert (m(0x61), m(0x69), m(0x70), m(0x28)) == (83, 92, 122, 125)
    assert len(set(macapi.VK_TO_MAC[ord(c)] for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")) == 36
    # all default hotkeys and step keys exist on a Mac keyboard
    for sc in config.default_config().profiles[0].shortcuts:
        assert m(keys.parse_hotkey(sc.hotkey)[1]) is not None, sc.hotkey

def test_engine_mod_vks_cover_mac_modifiers():
    # the hook reports modifiers as these VKs; the engine must know all of them
    for vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C):
        assert vk in eng._MOD_VK
        assert macapi.mac_keycode(vk) in macapi._MOD_FLAGS

def test_cmd_hotkey_fires():
    f = Fake()
    cfg = config.AppConfig(profiles=[config.Profile(name="B", exe="Bitwig Studio", delay_ms=0, steps="type {TEXT}",
                                                    shortcuts=[config.Shortcut(hotkey="cmd+alt+e", text="EQ+")])])
    e = eng.Engine(cfg)
    e._on_key(0x5B, True); e._on_key(0xA4, True)
    assert e._on_key(0x45, True) is True; wait_idle(e); time.sleep(0.05)
    assert ("type", "EQ+", "keys") in f.calls and f.calls[0] == ("release", (0x5B, 0xA4))

def test_settings_migrate_start_with_windows():
    s = config.Settings.from_dict({"start_with_windows": True})
    assert s.start_at_login is True
    assert config.Settings.from_dict({"start_at_login": False, "start_with_windows": True}).start_at_login is False

def test_launch_agent(tmp=None):
    d = tempfile.mkdtemp(); old = os.environ.get("HOME"); os.environ["HOME"] = d
    try:
        macapi.set_startup(True, ["/x/FX", "--tray"])
        assert macapi.is_startup()
        import plistlib
        data = plistlib.load(open(macapi._agent_path(), "rb"))
        assert data["ProgramArguments"] == ["/x/FX", "--tray"] and data["RunAtLoad"] is True
        macapi.set_startup(False); assert not macapi.is_startup()
    finally:
        if old is not None: os.environ["HOME"] = old

if __name__ == "__main__":
    import traceback
    ok = True
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            try: fn(); print("PASS", n)
            except Exception: ok = False; print("FAIL", n); traceback.print_exc()
    sys.exit(0 if ok else 1)
