#!/usr/bin/env python3
"""Configuration GUI for the Discord Ban Script.

Lets you set the bot token, server (guild) ID, and the target user by
their Discord handle. The handle is resolved to a stable user ID and
saved to config.json, which the hotkey script (ban.py) reads.

Run with:  python ban_gui.py
"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from discord_api import ban_user, load_config, resolve_handle, save_config


class BanApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Discord Ban Script")
        self.resizable(False, False)
        self.cfg = load_config()
        self._build()

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

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=3, pady=(10, 4))
        ttk.Button(btns, text="Resolve & Save target",
                   command=self.resolve_and_save).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Save settings only",
                   command=self.save_only).grid(row=0, column=1, padx=6)

        self.ban_btn = tk.Button(
            frm, text="BAN TARGET NOW", command=self.do_ban,
            bg="#c0392b", fg="white", font=("Helvetica", 13, "bold"),
            activebackground="#a83224", activeforeground="white", height=2)
        self.ban_btn.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 4))

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status, foreground="#2c3e50").grid(
            row=6, column=0, columnspan=3, sticky="w", **pad)

        note = ("Tip: bind your hotkey to run  ban.py  for one-press banning.\n"
                "The handle is resolved to an ID so renames don't break it.")
        ttk.Label(frm, text=note, foreground="#888",
                  justify="left").grid(row=7, column=0, columnspan=3,
                                       sticky="w", padx=10, pady=(2, 0))

    def _toggle_token(self):
        self.token_entry.config(show="" if self.show_var.get() else "•")

    def _collect(self):
        self.cfg["bot_token"] = self.token_var.get().strip()
        self.cfg["guild_id"] = self.guild_var.get().strip()
        self.cfg["target_handle"] = self.handle_var.get().strip()
        self.cfg["target_user_id"] = self.id_var.get().strip()

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

    def do_ban(self):
        self._collect()
        if not (self.cfg["bot_token"] and self.cfg["guild_id"]
                and self.cfg["target_user_id"]):
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

    # --- threading helpers so the UI stays responsive ---
    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _ui(self, fn):
        self.after(0, fn)


if __name__ == "__main__":
    BanApp().mainloop()
