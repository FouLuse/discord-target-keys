#!/usr/bin/env python3
"""Discord Target Keys — settings window, system tray, and global hotkeys.

Set a bot token, server (guild) ID, and a target user (by handle). Bind a
global hotkey to each action — Ban, Kick, Mute, Deafen — and trigger them
from anywhere, even with the window closed. The app lives in the system
tray and can optionally start with Windows.

Run with:  python ban_gui.py            (normal window)
           python ban_gui.py --tray     (start hidden in the tray)
"""

import os
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

from discord_api import (ban_user, get_member, kick_user, load_config,
                         resolve_handle, save_config, set_deaf, set_mute)

IS_WINDOWS = sys.platform.startswith("win")
APP_NAME = "DiscordTargetKeys"
DEFAULT_BINDS = {"ban": "Ctrl+Alt+B", "kick": "", "mute": "", "deafen": ""}

# action key -> (display label, hotkey id, confirm-on-manual-click)
ACTIONS = {
    "ban":    ("Ban",            1, True),
    "kick":   ("Kick",           2, True),
    "mute":   ("Mute (toggle)",  3, False),
    "deafen": ("Deafen (toggle)", 4, False),
}

SETUP_STEPS = (
    "First-time setup (about 5 minutes, one time only):\n\n"
    "1. Create your bot\n"
    "   - Click 'Open Discord Developer Portal' below.\n"
    "   - Click 'New Application', give it any name, then open the 'Bot' tab.\n"
    "   - Click 'Reset Token', then 'Copy'. Paste that into 'Bot token'.\n"
    "   - On the same page, turn ON 'Server Members Intent'.\n\n"
    "2. Add the bot to your server\n"
    "   - Open the 'OAuth2 > URL Generator' tab.\n"
    "   - Tick 'bot', then tick the permissions you want to use:\n"
    "       Ban Members, Kick Members, Mute Members, Deafen Members.\n"
    "   - Copy the link at the bottom, open it, and add the bot to your server.\n"
    "   - In Server Settings > Roles, drag the bot's role ABOVE the people\n"
    "     you want to moderate.\n\n"
    "3. Get your Server ID\n"
    "   - In Discord: User Settings > Advanced > turn on 'Developer Mode'.\n"
    "   - Right-click your server icon > 'Copy Server ID'. Paste it above.\n\n"
    "4. Set your target and binds\n"
    "   - Type the person's Discord username in 'Target handle', then\n"
    "     'Resolve & Save target'.\n"
    "   - Click 'Change bind' next to an action and press any key combo.\n\n"
    "Note: Mute and Deafen only work while the target is in a voice channel."
)

# ----------------------------------------------------------------------------
# Hotkey string helpers (platform-independent, unit-testable)
# ----------------------------------------------------------------------------

MOD_ORDER = ["ctrl", "alt", "shift", "win"]
MOD_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
MOD_FLAGS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
_MOD_ALIASES = {"control": "ctrl", "ctl": "ctrl", "windows": "win",
                "super": "win", "meta": "win", "cmd": "win"}

# Extra (non letter/digit/function) keys we support for global hotkeys.
SPECIAL_VK = {
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "BACKSPACE": 0x08,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "PAUSE": 0x13, "PRINTSCREEN": 0x2C,
}

# tkinter keysym -> our modifier name
_KEYSYM_MODS = {
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt", "Meta_L": "alt", "Meta_R": "alt",
    "Shift_L": "shift", "Shift_R": "shift",
    "Super_L": "win", "Super_R": "win", "Win_L": "win", "Win_R": "win",
}

# tkinter keysym -> our normalised key name (for non-printable keys)
_KEYSYM_KEYS = {
    "space": "SPACE", "Return": "ENTER", "Tab": "TAB", "BackSpace": "BACKSPACE",
    "Left": "LEFT", "Right": "RIGHT", "Up": "UP", "Down": "DOWN",
    "Prior": "PAGEUP", "Next": "PAGEDOWN", "Home": "HOME", "End": "END",
    "Insert": "INSERT", "Delete": "DELETE", "Pause": "PAUSE",
    "Print": "PRINTSCREEN",
}


def parse_hotkey(text):
    """'Ctrl+Alt+B' -> (['ctrl', 'alt'], 'B'). Empty string -> ([], '')."""
    parts = [p.strip() for p in (text or "").split("+") if p.strip()]
    if not parts:
        return [], ""
    key = parts[-1].upper()
    mods = {_MOD_ALIASES.get(p.lower(), p.lower()) for p in parts[:-1]}
    mods = {m for m in mods if m in MOD_FLAGS}
    return [m for m in MOD_ORDER if m in mods], key


def build_hotkey(mods, key):
    """(['ctrl','alt'], 'b') -> 'Ctrl+Alt+B'. No key -> ''."""
    if not key:
        return ""
    ordered = [MOD_LABELS[m] for m in MOD_ORDER if m in set(mods)]
    return "+".join(ordered + [key.upper()])


def hotkey_vk(key):
    """Virtual-key code for a key name (A-Z, 0-9, F1-F12, or a special)."""
    key = (key or "").upper()
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        return ord(key)
    if key.startswith("F") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 12:
            return 0x70 + (n - 1)
    return SPECIAL_VK.get(key)


def keysym_to_key(keysym):
    """Map a tkinter keysym to our key name, or None if unsupported."""
    if keysym in _KEYSYM_KEYS:
        return _KEYSYM_KEYS[keysym]
    if len(keysym) == 1 and (keysym.isalpha() or keysym.isdigit()):
        return keysym.upper()
    if keysym and keysym[0] in "Ff" and keysym[1:].isdigit():
        return keysym.upper()
    return None


def is_bare_printable(mods, key):
    """A single letter/digit with no modifier would hijack normal typing."""
    return (not mods) and len(key) == 1 and (key.isalpha() or key.isdigit())


# ----------------------------------------------------------------------------
# Auto-start with Windows (HKCU Run key)
# ----------------------------------------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}" --tray'


def is_autostart_enabled():
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled):
    if not IS_WINDOWS:
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ----------------------------------------------------------------------------
# Global hotkey manager (Windows only, via Win32 RegisterHotKey)
# ----------------------------------------------------------------------------

_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_WM_REREG = 0x8001  # WM_APP + 1


class HotkeyManager(threading.Thread):
    """Registers one global hotkey per action id and dispatches by id.

    on_trigger(action_id) runs on this thread when a hotkey fires.
    on_status(text) reports registration results.
    """

    def __init__(self, on_trigger, on_status=None):
        super().__init__(daemon=True)
        self.on_trigger = on_trigger
        self.on_status = on_status or (lambda *_: None)
        self._binds = {}          # id -> (mods, key)
        self._lock = threading.Lock()
        self._tid = None

    def set_binds(self, binds):
        with self._lock:
            self._binds = {i: v for i, v in binds.items() if v and v[1]}
        if self._tid is not None:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, _WM_REREG, 0, 0)

    def stop(self):
        if self._tid is not None:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)

    def _reregister(self, user32):
        for i in (1, 2, 3, 4):
            user32.UnregisterHotKey(None, i)
        with self._lock:
            binds = dict(self._binds)
        ok, bad = [], []
        for hid, (mods, key) in binds.items():
            vk = hotkey_vk(key)
            if vk is None:
                continue
            flags = MOD_NOREPEAT
            for m in mods:
                flags |= MOD_FLAGS.get(m, 0)
            if user32.RegisterHotKey(None, hid, flags, vk):
                ok.append(build_hotkey(mods, key))
            else:
                bad.append(build_hotkey(mods, key))
        if bad:
            self.on_status("Could not register (already in use): "
                           + ", ".join(bad))
        elif ok:
            self.on_status("Hotkeys active: " + ", ".join(ok))
        else:
            self.on_status("No hotkeys bound yet.")

    def run(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0x8000, 0x8000, 0)
        self._reregister(user32)
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            if msg.message == _WM_HOTKEY:
                try:
                    self.on_trigger(int(msg.wParam))
                except Exception:
                    pass
            elif msg.message == _WM_REREG:
                self._reregister(user32)
        for i in (1, 2, 3, 4):
            user32.UnregisterHotKey(None, i)


# ----------------------------------------------------------------------------
# Main application
# ----------------------------------------------------------------------------

class BanApp(tk.Tk):
    def __init__(self, start_hidden=False):
        super().__init__()
        self.title("Discord Target Keys")
        self.resizable(False, False)
        self.cfg = load_config()
        self.binds = self._load_binds()
        self.bind_vars = {}       # action -> StringVar showing current bind
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        self.hotkeys = None
        self.tray = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        if IS_WINDOWS:
            self._start_hotkeys()
            self._start_tray()
            if start_hidden:
                self.withdraw()

    # ---- binds model ----
    def _load_binds(self):
        binds = dict(DEFAULT_BINDS)
        saved = self.cfg.get("binds")
        if isinstance(saved, dict):
            binds.update({k: saved.get(k, "") for k in DEFAULT_BINDS})
        elif self.cfg.get("hotkey"):          # migrate v0.2 single hotkey
            binds["ban"] = self.cfg["hotkey"]
        return binds

    def _binds_for_manager(self):
        return {ACTIONS[a][1]: parse_hotkey(self.binds[a]) for a in ACTIONS}

    # ---- UI ----
    def _build(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self)
        frm.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        ttk.Label(frm, text="Bot token").grid(row=0, column=0, sticky="w", **pad)
        self.token_var = tk.StringVar(value=self.cfg.get("bot_token", ""))
        self.token_entry = ttk.Entry(frm, textvariable=self.token_var,
                                     width=46, show="•")
        self.token_entry.grid(row=0, column=1, **pad)
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Show", variable=self.show_var,
                        command=self._toggle_token).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="Server (guild) ID").grid(row=1, column=0, sticky="w", **pad)
        self.guild_var = tk.StringVar(value=self.cfg.get("guild_id", ""))
        ttk.Entry(frm, textvariable=self.guild_var, width=46).grid(
            row=1, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(frm, text="Target handle").grid(row=2, column=0, sticky="w", **pad)
        self.handle_var = tk.StringVar(value=self.cfg.get("target_handle", ""))
        ttk.Entry(frm, textvariable=self.handle_var, width=46).grid(
            row=2, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(frm, text="Resolved ID").grid(row=3, column=0, sticky="w", **pad)
        self.id_var = tk.StringVar(value=self.cfg.get("target_user_id", ""))
        ttk.Label(frm, textvariable=self.id_var, foreground="#555").grid(
            row=3, column=1, columnspan=2, sticky="w", **pad)

        ttk.Button(frm, text="First-time setup — need help getting these?",
                   command=self.show_help).grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=(2, 8))

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, pady=(2, 4))
        ttk.Button(btns, text="Resolve & Save target",
                   command=self.resolve_and_save).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Save settings only",
                   command=self.save_only).grid(row=0, column=1, padx=6)

        # Actions table
        tbl = ttk.LabelFrame(frm, text="Actions & hotkeys")
        tbl.grid(row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=(8, 4))
        for col, head in enumerate(("Action", "Hotkey", "", "", "")):
            ttk.Label(tbl, text=head, foreground="#666").grid(
                row=0, column=col, padx=6, pady=(4, 2), sticky="w")
        for r, action in enumerate(ACTIONS, start=1):
            label = ACTIONS[action][0]
            ttk.Label(tbl, text=label).grid(row=r, column=0, sticky="w",
                                            padx=6, pady=3)
            var = tk.StringVar(value=self.binds[action] or "(none)")
            self.bind_vars[action] = var
            ttk.Label(tbl, textvariable=var, width=16,
                      font=("Helvetica", 10, "bold")).grid(
                row=r, column=1, sticky="w", padx=6)
            ttk.Button(tbl, text="Change bind", width=12,
                       command=lambda a=action: self.capture_bind(a)).grid(
                row=r, column=2, padx=3)
            ttk.Button(tbl, text="Clear", width=6,
                       command=lambda a=action: self.clear_bind(a)).grid(
                row=r, column=3, padx=3)
            ttk.Button(tbl, text="Run now", width=8,
                       command=lambda a=action: self.run_action_manual(a)).grid(
                row=r, column=4, padx=3)

        # Background options
        opt = ttk.Frame(frm)
        opt.grid(row=7, column=0, columnspan=3, sticky="ew", padx=10, pady=(2, 4))
        self.autostart_chk = ttk.Checkbutton(
            opt, text="Start with Windows (runs in the system tray)",
            variable=self.autostart_var, command=self.toggle_autostart)
        self.autostart_chk.grid(row=0, column=0, sticky="w")
        if not IS_WINDOWS:
            self.autostart_chk.state(["disabled"])
            ttk.Label(opt, text="(Hotkeys & auto-start work on Windows.)",
                      foreground="#888").grid(row=1, column=0, sticky="w")

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status, foreground="#2c3e50",
                  wraplength=440, justify="left").grid(
            row=8, column=0, columnspan=3, sticky="w", **pad)

        note = ("Closing this window keeps the app running in the tray so the "
                "hotkeys still work. Quit from the tray icon to stop it.")
        ttk.Label(frm, text=note, foreground="#888", wraplength=440,
                  justify="left").grid(row=9, column=0, columnspan=3,
                                       sticky="w", padx=10, pady=(2, 0))

    def _toggle_token(self):
        self.token_entry.config(show="" if self.show_var.get() else "•")

    def show_help(self):
        win = tk.Toplevel(self)
        win.title("First-time setup")
        win.resizable(False, False)
        win.transient(self)
        frm = ttk.Frame(win)
        frm.grid(row=0, column=0, padx=14, pady=14)
        txt = tk.Text(frm, width=66, height=26, wrap="word",
                      borderwidth=0, background=self.cget("background"))
        txt.insert("1.0", SETUP_STEPS)
        txt.config(state="disabled")
        txt.grid(row=0, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(frm, text="Open Discord Developer Portal",
                   command=lambda: webbrowser.open(
                       "https://discord.com/developers/applications")).grid(
            row=1, column=0, padx=4, sticky="w")
        ttk.Button(frm, text="Close", command=win.destroy).grid(
            row=1, column=1, padx=4, sticky="e")

    # ---- game-style key capture ----
    def capture_bind(self, action):
        win = tk.Toplevel(self)
        win.title(f"Bind: {ACTIONS[action][0]}")
        win.resizable(False, False)
        win.transient(self)
        frm = ttk.Frame(win)
        frm.grid(row=0, column=0, padx=22, pady=20)
        prompt = tk.StringVar(value="Press any key or combination…")
        ttk.Label(frm, textvariable=prompt,
                  font=("Helvetica", 12, "bold")).grid(row=0, column=0)
        ttk.Label(frm, foreground="#888",
                  text="Esc = cancel   •   Backspace = clear this bind").grid(
            row=1, column=0, pady=(8, 0))

        held = set()

        def finish(value):
            self._set_bind(action, value)
            win.destroy()

        def on_press(e):
            ks = e.keysym
            if ks in _KEYSYM_MODS:
                held.add(_KEYSYM_MODS[ks])
                mods = [m for m in MOD_ORDER if m in held]
                prompt.set("+".join(MOD_LABELS[m] for m in mods) + "+…"
                           if mods else "Press any key or combination…")
                return
            if ks == "Escape":
                win.destroy()
                return
            if ks in ("BackSpace", "Delete") and not held:
                finish("")
                return
            key = keysym_to_key(ks)
            if key is None:
                return
            mods = [m for m in MOD_ORDER if m in held]
            if is_bare_printable(mods, key):
                if not messagebox.askyesno(
                        "Bare key?",
                        f"'{key}' has no modifier, so it will be captured "
                        "system-wide and you won't be able to type it normally.\n\n"
                        "Use it anyway?", parent=win):
                    return
            finish(build_hotkey(mods, key))

        def on_release(e):
            ks = e.keysym
            if ks in _KEYSYM_MODS:
                held.discard(_KEYSYM_MODS[ks])

        win.bind("<KeyPress>", on_press)
        win.bind("<KeyRelease>", on_release)
        win.focus_force()
        win.grab_set()

    def _set_bind(self, action, value):
        self.binds[action] = value
        self.bind_vars[action].set(value or "(none)")
        self._collect()
        save_config(self.cfg)
        if self.hotkeys:
            self.hotkeys.set_binds(self._binds_for_manager())
        self.status.set(f"{ACTIONS[action][0]} bind: {value or 'cleared'}")

    def clear_bind(self, action):
        self._set_bind(action, "")

    def toggle_autostart(self):
        try:
            set_autostart(self.autostart_var.get())
            self.status.set("Start with Windows: "
                            + ("on" if self.autostart_var.get() else "off"))
        except Exception as e:
            messagebox.showerror("Auto-start failed", str(e))
            self.autostart_var.set(is_autostart_enabled())

    # ---- config plumbing ----
    def _collect(self):
        self.cfg["bot_token"] = self.token_var.get().strip()
        self.cfg["guild_id"] = self.guild_var.get().strip()
        self.cfg["target_handle"] = self.handle_var.get().strip()
        self.cfg["target_user_id"] = self.id_var.get().strip()
        self.cfg["binds"] = dict(self.binds)
        self.cfg.pop("hotkey", None)

    def save_only(self):
        self._collect()
        save_config(self.cfg)
        self.status.set("Settings saved.")

    def resolve_and_save(self):
        self._collect()
        if not (self.cfg["bot_token"] and self.cfg["guild_id"]):
            messagebox.showerror("Missing info",
                                 "Enter the bot token and server ID first.")
            return
        if not self.cfg["target_handle"]:
            messagebox.showerror("Missing info", "Enter a target handle.")
            return
        self.status.set("Resolving handle...")
        self._run_bg(self._resolve_worker)

    def _resolve_worker(self):
        try:
            uid, label = resolve_handle(
                self.cfg["bot_token"], self.cfg["guild_id"],
                self.cfg["target_handle"])
        except Exception as e:
            self._ui(lambda: self.status.set(f"Error: {e}"))
            self._ui(lambda: messagebox.showerror("Resolve failed", str(e)))
            return
        self.cfg["target_user_id"] = uid
        save_config(self.cfg)
        self._ui(lambda: self.id_var.set(uid))
        self._ui(lambda: self.status.set(f"Saved target: {label} ({uid})"))

    def _ready(self):
        return bool(self.cfg.get("bot_token") and self.cfg.get("guild_id")
                    and self.cfg.get("target_user_id"))

    # ---- running actions ----
    def run_action_manual(self, action):
        """Triggered by the on-screen 'Run now' button (with confirm if needed)."""
        self._collect()
        if not self._ready():
            messagebox.showerror(
                "Not ready",
                "Need bot token, server ID, and a resolved target ID.\n"
                "Use 'Resolve & Save target' first.")
            return
        if ACTIONS[action][2]:
            label = self.cfg.get("target_handle") or self.cfg["target_user_id"]
            verb = ACTIONS[action][0]
            if not messagebox.askyesno("Confirm", f"{verb} {label}?"):
                return
        self._run_bg(lambda: self._do_action(action))

    def _trigger_by_id(self, hotkey_id):
        """Triggered by a global hotkey — silent, no dialogs."""
        for action, (_, hid, _) in ACTIONS.items():
            if hid == hotkey_id:
                self._run_bg(lambda a=action: self._do_action(a))
                return

    def _do_action(self, action):
        cfg = load_config()                # trust saved config (window may be hidden)
        if not (cfg.get("bot_token") and cfg.get("guild_id")
                and cfg.get("target_user_id")):
            self._set_status("Hotkey pressed, but setup isn't complete yet.")
            return
        token, guild = cfg["bot_token"], cfg["guild_id"]
        uid = cfg["target_user_id"]
        label = cfg.get("target_handle") or uid
        try:
            if action == "ban":
                ban_user(token, guild, uid)
                self._set_status(f"Banned {label}.")
            elif action == "kick":
                kick_user(token, guild, uid)
                self._set_status(f"Kicked {label}.")
            elif action == "mute":
                cur = bool(get_member(token, guild, uid).get("mute"))
                set_mute(token, guild, uid, not cur)
                self._set_status(f"{'Unmuted' if cur else 'Muted'} {label}.")
            elif action == "deafen":
                cur = bool(get_member(token, guild, uid).get("deaf"))
                set_deaf(token, guild, uid, not cur)
                self._set_status(f"{'Undeafened' if cur else 'Deafened'} {label}.")
        except Exception as e:
            self._set_status(f"{ACTIONS[action][0]} failed: {e}")

    def _set_status(self, text):
        try:
            self.after(0, lambda: self.status.set(text))
        except Exception:
            pass

    # ---- hotkey + tray lifecycle ----
    def _start_hotkeys(self):
        self.hotkeys = HotkeyManager(on_trigger=self._trigger_by_id,
                                     on_status=self._set_status)
        self.hotkeys.set_binds(self._binds_for_manager())
        self.hotkeys.start()

    def _start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            return
        img = Image.new("RGB", (64, 64), "#c0392b")
        d = ImageDraw.Draw(img)
        d.ellipse([12, 12, 52, 52], outline="white", width=6)
        d.line([20, 44, 44, 20], fill="white", width=6)
        menu = pystray.Menu(
            pystray.MenuItem("Open settings", self._tray_open, default=True),
            pystray.MenuItem("Start with Windows", self._tray_toggle_autostart,
                             checked=lambda item: is_autostart_enabled()),
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self.tray = pystray.Icon(APP_NAME, img, "Discord Target Keys", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_open(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_toggle_autostart(self, icon=None, item=None):
        set_autostart(not is_autostart_enabled())
        self.after(0, lambda: self.autostart_var.set(is_autostart_enabled()))

    def _tray_quit(self, icon=None, item=None):
        if self.hotkeys:
            self.hotkeys.stop()
        if self.tray:
            self.tray.stop()
        self.after(0, self.destroy)

    def hide_to_tray(self):
        if IS_WINDOWS and self.tray is not None:
            self.withdraw()
        else:
            self.destroy()

    # ---- threading helpers ----
    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _ui(self, fn):
        self.after(0, fn)


if __name__ == "__main__":
    BanApp(start_hidden="--tray" in sys.argv).mainloop()
