#!/usr/bin/env python3
"""Discord Ban Script — settings window, system tray, and global hotkey.

Set a bot token, server (guild) ID, and a target user (by handle). The app
lives in the system tray; pressing the global hotkey (default Ctrl+Alt+B)
instantly bans the saved target. It can optionally start with Windows.

Run with:  python ban_gui.py            (normal window)
           python ban_gui.py --tray     (start hidden in the tray)
"""

import os
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

from discord_api import ban_user, load_config, resolve_handle, save_config

IS_WINDOWS = sys.platform.startswith("win")
APP_NAME = "DiscordBanScript"
DEFAULT_HOTKEY = "Ctrl+Alt+B"

SETUP_STEPS = (
    "First-time setup (about 5 minutes, one time only):\n\n"
    "1. Create your bot\n"
    "   - Click 'Open Discord Developer Portal' below.\n"
    "   - Click 'New Application', give it any name, then open the 'Bot' tab.\n"
    "   - Click 'Reset Token', then 'Copy'. Paste that into 'Bot token'.\n"
    "   - On the same page, turn ON 'Server Members Intent'.\n\n"
    "2. Add the bot to your server\n"
    "   - Open the 'OAuth2 > URL Generator' tab.\n"
    "   - Tick 'bot', then tick 'Ban Members'.\n"
    "   - Copy the link at the bottom, open it, and add the bot to your server.\n"
    "   - In Server Settings > Roles, drag the bot's role ABOVE the people\n"
    "     you want to be able to ban.\n\n"
    "3. Get your Server ID\n"
    "   - In Discord: User Settings > Advanced > turn on 'Developer Mode'.\n"
    "   - Right-click your server icon > 'Copy Server ID'. Paste it above.\n\n"
    "4. Set your target\n"
    "   - Type the person's Discord username in 'Target handle'.\n"
    "   - Click 'Resolve & Save target'. Done.\n\n"
    "5. (Optional) Pick your ban hotkey and 'Start with Windows' so the app\n"
    "   runs quietly in the tray and one keypress bans your target."
)

# ----------------------------------------------------------------------------
# Hotkey string helpers (platform-independent, so they can be unit tested)
# ----------------------------------------------------------------------------

MOD_ORDER = ["ctrl", "alt", "shift", "win"]
MOD_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
MOD_FLAGS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
_MOD_ALIASES = {"control": "ctrl", "ctl": "ctrl", "windows": "win",
                "super": "win", "meta": "win", "cmd": "win"}


def parse_hotkey(text):
    """'Ctrl+Alt+B' -> (['ctrl', 'alt'], 'B'). Order of modifiers is normalised."""
    parts = [p.strip() for p in (text or "").split("+") if p.strip()]
    if not parts:
        return [], ""
    key = parts[-1].upper()
    mods = {_MOD_ALIASES.get(p.lower(), p.lower()) for p in parts[:-1]}
    mods = {m for m in mods if m in MOD_FLAGS}
    ordered = [m for m in MOD_ORDER if m in mods]
    return ordered, key


def build_hotkey(mods, key):
    """(['ctrl','alt'], 'b') -> 'Ctrl+Alt+B'."""
    ordered = [MOD_LABELS[m] for m in MOD_ORDER if m in set(mods)]
    return "+".join(ordered + [key.upper()]) if key else "+".join(ordered)


def hotkey_vk(key):
    """Virtual-key code for a single key name (A-Z, 0-9, F1-F12)."""
    key = (key or "").upper()
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        return ord(key)
    if key.startswith("F") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 12:
            return 0x70 + (n - 1)
    return None


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
    except FileNotFoundError:
        return False
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
# Global hotkey listener (Windows only, via Win32 RegisterHotKey)
# ----------------------------------------------------------------------------

_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_WM_REREG = 0x8001  # WM_APP + 1


class HotkeyListener(threading.Thread):
    """Registers a global hotkey on its own thread and runs a message loop.

    on_trigger() is called (on this thread) each time the hotkey fires.
    on_status(text) reports whether registration succeeded.
    """

    def __init__(self, on_trigger, on_status=None):
        super().__init__(daemon=True)
        self.on_trigger = on_trigger
        self.on_status = on_status or (lambda *_: None)
        self._combo = ([], "")
        self._lock = threading.Lock()
        self._tid = None
        self._id = 1

    def set_combo(self, mods, key):
        with self._lock:
            self._combo = (list(mods), key)
        if self._tid is not None:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, _WM_REREG, 0, 0)

    def stop(self):
        if self._tid is not None:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)

    def _register(self, user32):
        user32.UnregisterHotKey(None, self._id)
        with self._lock:
            mods, key = self._combo
        vk = hotkey_vk(key)
        if vk is None:
            self.on_status("No valid hotkey set.")
            return
        flags = MOD_NOREPEAT
        for m in mods:
            flags |= MOD_FLAGS.get(m, 0)
        if user32.RegisterHotKey(None, self._id, flags, vk):
            self.on_status(f"Hotkey active: {build_hotkey(mods, key)}")
        else:
            self.on_status(f"Could not register {build_hotkey(mods, key)} "
                           "(another app may be using it).")

    def run(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        # Force the thread to own a message queue before posting to it.
        user32.PeekMessageW(ctypes.byref(msg), None, 0x8000, 0x8000, 0)
        self._register(user32)
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            if msg.message == _WM_HOTKEY:
                try:
                    self.on_trigger()
                except Exception:
                    pass
            elif msg.message == _WM_REREG:
                self._register(user32)
        user32.UnregisterHotKey(None, self._id)


# ----------------------------------------------------------------------------
# Main application
# ----------------------------------------------------------------------------

class BanApp(tk.Tk):
    def __init__(self, start_hidden=False):
        super().__init__()
        self.title("Discord Ban Script")
        self.resizable(False, False)
        self.cfg = load_config()
        self.hotkey_str = self.cfg.get("hotkey") or DEFAULT_HOTKEY
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        self.hotkey = None
        self.tray = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        if IS_WINDOWS:
            self._start_hotkey()
            self._start_tray()
            if start_hidden:
                self.withdraw()

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
        btns.grid(row=5, column=0, columnspan=3, pady=(6, 4))
        ttk.Button(btns, text="Resolve & Save target",
                   command=self.resolve_and_save).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Save settings only",
                   command=self.save_only).grid(row=0, column=1, padx=6)

        # Hotkey + auto-start row
        opt = ttk.LabelFrame(frm, text="Background & hotkey")
        opt.grid(row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=(8, 4))
        ttk.Label(opt, text="Ban hotkey:").grid(row=0, column=0, sticky="w",
                                                 padx=8, pady=6)
        self.hotkey_lbl = tk.StringVar(value=self.hotkey_str)
        ttk.Label(opt, textvariable=self.hotkey_lbl,
                  font=("Helvetica", 10, "bold")).grid(row=0, column=1,
                                                        sticky="w", pady=6)
        change_btn = ttk.Button(opt, text="Change…", command=self.change_hotkey)
        change_btn.grid(row=0, column=2, sticky="e", padx=8, pady=6)
        self.autostart_chk = ttk.Checkbutton(
            opt, text="Start with Windows (runs in the system tray)",
            variable=self.autostart_var, command=self.toggle_autostart)
        self.autostart_chk.grid(row=1, column=0, columnspan=3, sticky="w",
                                padx=8, pady=(0, 6))
        if not IS_WINDOWS:
            change_btn.state(["disabled"])
            self.autostart_chk.state(["disabled"])
            ttk.Label(opt, text="(Hotkey & auto-start work on Windows.)",
                      foreground="#888").grid(row=2, column=0, columnspan=3,
                                              sticky="w", padx=8, pady=(0, 6))

        self.ban_btn = tk.Button(
            frm, text="BAN TARGET NOW", command=self.do_ban,
            bg="#c0392b", fg="white", font=("Helvetica", 13, "bold"),
            activebackground="#a83224", activeforeground="white", height=2)
        self.ban_btn.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 4))

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status, foreground="#2c3e50").grid(
            row=8, column=0, columnspan=3, sticky="w", **pad)

        note = ("Closing this window keeps the app running in the tray so the "
                "hotkey still works. Quit from the tray icon to stop it.")
        ttk.Label(frm, text=note, foreground="#888", wraplength=420,
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
        txt = tk.Text(frm, width=64, height=24, wrap="word",
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

    # ---- hotkey config dialog ----
    def change_hotkey(self):
        mods, key = parse_hotkey(self.hotkey_str)
        win = tk.Toplevel(self)
        win.title("Set ban hotkey")
        win.resizable(False, False)
        win.transient(self)
        frm = ttk.Frame(win)
        frm.grid(row=0, column=0, padx=16, pady=16)

        ttk.Label(frm, text="Hold modifiers + pick a key:").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        vars_ = {}
        for i, m in enumerate(MOD_ORDER):
            v = tk.BooleanVar(value=(m in mods))
            vars_[m] = v
            ttk.Checkbutton(frm, text=MOD_LABELS[m], variable=v).grid(
                row=1, column=i, sticky="w", padx=4)

        ttk.Label(frm, text="Key:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        keys = ([chr(c) for c in range(ord("A"), ord("Z") + 1)]
                + [str(d) for d in range(10)]
                + [f"F{n}" for n in range(1, 13)])
        key_var = tk.StringVar(value=key if key in keys else "B")
        ttk.Combobox(frm, textvariable=key_var, values=keys, width=6,
                     state="readonly").grid(row=2, column=1, sticky="w",
                                            pady=(10, 0))

        def save():
            chosen = [m for m in MOD_ORDER if vars_[m].get()]
            if not chosen:
                messagebox.showwarning(
                    "Add a modifier",
                    "Pick at least one of Ctrl/Alt/Shift/Win so the hotkey "
                    "doesn't fire while you're typing.")
                return
            self.hotkey_str = build_hotkey(chosen, key_var.get())
            self.hotkey_lbl.set(self.hotkey_str)
            self.cfg["hotkey"] = self.hotkey_str
            self._collect()
            save_config(self.cfg)
            if self.hotkey:
                self.hotkey.set_combo(chosen, key_var.get())
            win.destroy()

        ttk.Button(frm, text="Save", command=save).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Button(frm, text="Cancel", command=win.destroy).grid(
            row=3, column=2, columnspan=2, sticky="e", pady=(14, 0))

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
        self.cfg["hotkey"] = self.hotkey_str

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

    # ---- banning ----
    def do_ban(self):
        self._collect()
        if not self._ready_to_ban():
            messagebox.showerror(
                "Not ready",
                "Need bot token, server ID, and a resolved target ID.\n"
                "Use 'Resolve & Save target' first.")
            return
        label = self.cfg.get("target_handle") or self.cfg["target_user_id"]
        if not messagebox.askyesno("Confirm ban", f"Ban {label}?"):
            return
        self.status.set("Banning...")
        self.ban_btn.config(state="disabled")
        self._run_bg(self._ban_worker)

    def _ban_worker(self):
        try:
            ban_user(self.cfg["bot_token"], self.cfg["guild_id"],
                     self.cfg["target_user_id"])
        except Exception as e:
            self._ui(lambda: self.status.set(f"Ban failed: {e}"))
            self._ui(lambda: messagebox.showerror("Ban failed", str(e)))
        else:
            label = self.cfg.get("target_handle") or self.cfg["target_user_id"]
            self._ui(lambda: self.status.set(f"Banned {label}."))
        finally:
            self._ui(lambda: self.ban_btn.config(state="normal"))

    def _ready_to_ban(self):
        return bool(self.cfg.get("bot_token") and self.cfg.get("guild_id")
                    and self.cfg.get("target_user_id"))

    def _ban_silent(self):
        """Instant ban with no dialogs — used by the hotkey and tray."""
        self._collect_from_disk()
        if not self._ready_to_ban():
            self._set_status("Hotkey pressed, but setup isn't complete yet.")
            return
        label = self.cfg.get("target_handle") or self.cfg["target_user_id"]
        try:
            ban_user(self.cfg["bot_token"], self.cfg["guild_id"],
                     self.cfg["target_user_id"])
            self._set_status(f"Banned {label} (via hotkey).")
        except Exception as e:
            self._set_status(f"Hotkey ban failed: {e}")

    def _collect_from_disk(self):
        # The hotkey may fire while the window is hidden; trust saved config.
        self.cfg = load_config()

    def _set_status(self, text):
        try:
            self.after(0, lambda: self.status.set(text))
        except Exception:
            pass

    # ---- hotkey + tray lifecycle ----
    def _start_hotkey(self):
        mods, key = parse_hotkey(self.hotkey_str)
        self.hotkey = HotkeyListener(
            on_trigger=lambda: self._run_bg(self._ban_silent),
            on_status=self._set_status)
        self.hotkey.set_combo(mods, key)
        self.hotkey.start()

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
            pystray.MenuItem("Ban now", self._tray_ban),
            pystray.MenuItem("Start with Windows", self._tray_toggle_autostart,
                             checked=lambda item: is_autostart_enabled()),
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self.tray = pystray.Icon(APP_NAME, img, "Discord Ban Script", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_open(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_ban(self, icon=None, item=None):
        self._run_bg(self._ban_silent)

    def _tray_toggle_autostart(self, icon=None, item=None):
        set_autostart(not is_autostart_enabled())
        self.after(0, lambda: self.autostart_var.set(is_autostart_enabled()))

    def _tray_quit(self, icon=None, item=None):
        if self.hotkey:
            self.hotkey.stop()
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
