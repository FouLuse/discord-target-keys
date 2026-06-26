#!/usr/bin/env python3
"""Lightweight smoke tests — run on every push by CI and locally.

No display or Windows needed: tkinter is stubbed and all Discord HTTP calls
are mocked. Run with:  python run_tests.py
Exits non-zero if anything fails.
"""

import sys
import types


def _stub_tkinter():
    for name in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
        sys.modules[name] = types.ModuleType(name)

    class _Dummy:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _):
            return _Dummy()

        def __call__(self, *a, **k):
            return _Dummy()

    tk = sys.modules["tkinter"]
    for attr in ("Tk", "StringVar", "BooleanVar", "Text", "Toplevel",
                 "Frame", "Label"):
        setattr(tk, attr, _Dummy)


def test_discord_api():
    import discord_api as d

    class R:
        def __init__(self, code, data=None, text="", content=b"x"):
            self.status_code = code
            self._d = data
            self.text = text
            self.content = content

        def json(self):
            return self._d

    # ban
    d.requests.put = lambda *a, **k: R(204)
    assert "Banned" in d.ban_user("t", "g", "1")

    # kick
    seen = {}
    d.requests.delete = lambda url, **k: seen.update(url=url) or R(204)
    assert "Kicked" in d.kick_user("t", "g", "123")
    assert seen["url"].endswith("/guilds/g/members/123")

    # member read + mute/deafen
    d.requests.get = lambda *a, **k: R(200, {"mute": False, "deaf": True})
    assert d.get_member("t", "g", "1")["deaf"] is True
    body = {}
    d.requests.patch = lambda url, json=None, **k: body.update(json) or R(204, content=b"")
    d.set_mute("t", "g", "1", True)
    assert body == {"mute": True}
    body.clear()
    d.set_deaf("t", "g", "1", False)
    assert body == {"deaf": False}

    # friendly errors
    d.requests.patch = lambda *a, **k: R(400, text='{"message":"not connected to voice"}')
    try:
        d.set_mute("t", "g", "1", True)
        raise AssertionError("expected voice error")
    except RuntimeError as e:
        assert "voice" in str(e).lower()

    d.requests.delete = lambda *a, **k: R(403, text="no perms")
    try:
        d.kick_user("t", "g", "1")
        raise AssertionError("expected 403")
    except RuntimeError as e:
        assert "Kick Members" in str(e)


def test_hotkey_helpers(bg):
    assert bg.parse_hotkey("Ctrl+Alt+B") == (["ctrl", "alt"], "B")
    assert bg.build_hotkey(["alt", "ctrl"], "b") == "Ctrl+Alt+B"

    # letters / digits / function keys
    assert bg.hotkey_vk("B") == 0x42
    assert bg.hotkey_vk("F24") == 0x87

    # punctuation + numpad names map to the right VKs
    assert bg.keysym_to_key("semicolon") == "SEMICOLON"
    assert bg.hotkey_vk("SEMICOLON") == 0xBA
    assert bg.keysym_to_key("KP_1") == "NUM1"
    assert bg.hotkey_vk("NUM1") == 0x61
    assert bg.hotkey_vk("VK222") == 222

    # tokens never contain '+', so parse/build round-trips
    assert bg.parse_hotkey(bg.build_hotkey(["ctrl"], "NUMADD")) == (["ctrl"], "NUMADD")

    # bare typing-key guard
    assert bg.is_bare_printable([], "SEMICOLON") is True
    assert bg.is_bare_printable(["alt"], "B") is False
    assert bg.is_bare_printable([], "F5") is False


def test_key_capture(bg):
    # The registered code must be the real keycode, even when the keysym
    # name would resolve to a different (wrong) code.
    assert bg.key_name_from_event("semicolon", 0xBA, ";") == "SEMICOLON"
    assert bg.key_name_from_event("weird", 0xAD, "") == "VK173"
    assert bg.key_name_from_event("emptystr", 0xDB, "[") == "["


def test_bind_migration(bg):
    app = bg.BanApp.__new__(bg.BanApp)
    app.cfg = {"binds": {
        "ban": {"label": "Ctrl+Alt+B", "mods": ["ctrl", "alt"], "vk": 66},
        "kick": {"label": "Num1", "mods": [], "vk": 0x61},
        "mute": "Ctrl+Shift+Semicolon",   # legacy string
        "deafen": None}}
    app.binds = app._load_binds()
    assert app.binds["kick"]["vk"] == 0x61
    assert app.binds["mute"]["vk"] == 0xBA
    mgr = bg.BanApp._binds_for_manager(app)
    assert mgr[1] == (["ctrl", "alt"], 66)
    assert mgr[2] == ([], 0x61)
    assert mgr[3] == (["ctrl", "shift"], 0xBA)
    assert mgr[4] == ([], 0)

    # v0.2 single-hotkey migration
    app2 = bg.BanApp.__new__(bg.BanApp)
    app2.cfg = {"hotkey": "Ctrl+Alt+K"}
    assert app2._load_binds()["ban"]["vk"] == ord("K")


def main():
    _stub_tkinter()
    import importlib.util
    spec = importlib.util.spec_from_file_location("ban_gui", "ban_gui.py")
    bg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bg)

    tests = [
        ("discord_api", lambda: test_discord_api()),
        ("hotkey_helpers", lambda: test_hotkey_helpers(bg)),
        ("key_capture", lambda: test_key_capture(bg)),
        ("bind_migration", lambda: test_bind_migration(bg)),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    if failed:
        print(f"\n{failed} test group(s) failed.")
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
