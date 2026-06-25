"""Shared Discord REST API helpers for the ban tool.

Uses the Discord HTTP API (v10) directly via `requests`, so no heavy
bot framework is needed. Only a bot token with the Ban Members
permission is required.
"""

import json
import os
import sys

import requests

API = "https://discord.com/api/v10"


def _config_dir():
    """Where config.json lives.

    When packaged as a standalone .exe (PyInstaller sets sys.frozen), the
    script runs from a temporary folder that is wiped on exit, so settings
    are stored in a stable per-user location (%APPDATA% on Windows, the
    home folder elsewhere). In normal development it sits next to the code.
    """
    if getattr(sys, "frozen", False):
        base = (os.environ.get("APPDATA")
                or os.environ.get("XDG_CONFIG_HOME")
                or os.path.expanduser("~"))
        path = os.path.join(base, "DiscordBanScript")
        os.makedirs(path, exist_ok=True)
        return path
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_config_dir(), "config.json")

DEFAULT_CONFIG = {
    "bot_token": "",
    "guild_id": "",
    "target_user_id": "",
    "target_handle": "",
    "hotkey": "Ctrl+Alt+B",
}


def load_config():
    """Load config.json, filling in any missing keys with defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            try:
                cfg.update(json.load(f))
            except json.JSONDecodeError:
                pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _headers(token):
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBanScript (https://example.com, 1.0)",
    }


def resolve_handle(token, guild_id, handle):
    """Resolve a Discord handle (username) to a user ID for a guild.

    If `handle` is already a numeric ID, it is returned as-is (verified).
    Returns (user_id, display_label) or raises RuntimeError with a message.
    """
    handle = handle.strip().lstrip("@")
    if not handle:
        raise RuntimeError("No handle provided.")

    # If they pasted a raw numeric ID, use it directly.
    if handle.isdigit():
        return handle, handle

    # Strip a legacy discriminator if present (e.g. name#1234).
    query = handle.split("#")[0]

    url = f"{API}/guilds/{guild_id}/members/search"
    resp = requests.get(
        url, headers=_headers(token), params={"query": query, "limit": 100}, timeout=15
    )
    if resp.status_code == 401:
        raise RuntimeError("Invalid bot token (401 Unauthorized).")
    if resp.status_code == 403:
        raise RuntimeError(
            "Bot lacks permission to search members, or the Server Members "
            "Intent is not enabled in the Developer Portal (403)."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Search failed ({resp.status_code}): {resp.text}")

    members = resp.json()
    if not members:
        raise RuntimeError(f"No member found matching '{handle}'.")

    # Prefer an exact username match; otherwise take the first result.
    target = handle.lower()
    best = None
    for m in members:
        user = m.get("user", {})
        username = (user.get("username") or "").lower()
        if username == target:
            best = user
            break
    if best is None:
        best = members[0].get("user", {})

    user_id = best.get("id")
    label = best.get("global_name") or best.get("username") or user_id
    if not user_id:
        raise RuntimeError("Member found but had no user ID.")
    return user_id, label


def ban_user(token, guild_id, user_id, reason="Banned via Discord Ban Script",
             delete_message_seconds=0):
    """Ban a user from a guild. Returns a human-readable result string.

    Raises RuntimeError on failure.
    """
    url = f"{API}/guilds/{guild_id}/bans/{user_id}"
    headers = _headers(token)
    if reason:
        headers["X-Audit-Log-Reason"] = reason[:512]
    body = {}
    if delete_message_seconds:
        body["delete_message_seconds"] = int(delete_message_seconds)

    resp = requests.put(url, headers=headers, json=body, timeout=15)

    if resp.status_code in (200, 204):
        return f"Banned user {user_id}."
    if resp.status_code == 401:
        raise RuntimeError("Invalid bot token (401 Unauthorized).")
    if resp.status_code == 403:
        raise RuntimeError(
            "Forbidden (403): the bot needs the 'Ban Members' permission and "
            "its role must be higher than the target's highest role."
        )
    if resp.status_code == 404:
        raise RuntimeError("Not found (404): check the server ID and user ID.")
    raise RuntimeError(f"Ban failed ({resp.status_code}): {resp.text}")
