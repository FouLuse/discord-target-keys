#!/usr/bin/env python3
"""Instant ban — bind this to a keyboard hotkey.

Running this script bans the target user saved in config.json with no
prompts. Configure the target first using ban_gui.py.

Exit codes: 0 = success, 1 = failure (so hotkey tools can detect errors).
"""

import sys

from discord_api import ban_user, load_config


def notify(title, message):
    """Best-effort desktop notification; falls back to printing."""
    print(f"{title}: {message}")
    try:
        if sys.platform == "darwin":
            import subprocess
            safe = message.replace('"', "'")
            t = title.replace('"', "'")
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{safe}" with title "{t}"'],
                check=False,
            )
        elif sys.platform.startswith("linux"):
            import subprocess
            subprocess.run(["notify-send", title, message], check=False)
        elif sys.platform.startswith("win"):
            # Simple message box on Windows.
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        pass


def main():
    cfg = load_config()
    missing = [k for k in ("bot_token", "guild_id", "target_user_id") if not cfg.get(k)]
    if missing:
        notify("Discord Ban — not configured",
               "Run ban_gui.py and set: " + ", ".join(missing))
        return 1

    label = cfg.get("target_handle") or cfg["target_user_id"]
    try:
        ban_user(cfg["bot_token"], cfg["guild_id"], cfg["target_user_id"])
    except Exception as e:
        notify("Discord Ban — FAILED", f"{label}: {e}")
        return 1

    notify("Discord Ban — success", f"Banned {label}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
