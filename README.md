# Discord Ban Script

Ban one pre-set user from your Discord server with a single hotkey press.
A small GUI lets you set (and change) the target by their Discord handle.

## What's included

- `ban.py` — the one-press ban. Bind a hotkey to this. No prompts.
- `ban_gui.py` — settings window: set token, server, and target handle; also has a manual **BAN TARGET NOW** button.
- `discord_api.py` — shared Discord API helpers (no extra bot framework needed).
- `config.json` — saved settings (created/updated automatically).

## One-time setup

### 1. Install Python and the one dependency

You need Python 3.8+. Then install `requests`:

```
pip install requests
```

(`tkinter`, used by the GUI, ships with most Python installs. On Debian/Ubuntu: `sudo apt install python3-tk`.)

### 2. Create a Discord bot

1. Go to https://discord.com/developers/applications and click **New Application**.
2. Open the **Bot** tab → **Add Bot**.
3. Click **Reset Token**, then **Copy** the token. Keep it secret — anyone with it controls the bot.
4. On the same Bot page, scroll to **Privileged Gateway Intents** and turn on **Server Members Intent** (this lets the bot look up a user by handle).

### 3. Invite the bot to your server with ban permission

1. Go to **OAuth2 → URL Generator**.
2. Under **Scopes** check `bot`.
3. Under **Bot Permissions** check **Ban Members**.
4. Copy the generated URL at the bottom, open it in your browser, and add the bot to your server.

> Important: in **Server Settings → Roles**, drag the bot's role **above** the roles of anyone you want to ban. A bot can't ban someone whose highest role is above its own.

### 4. Get your Server (Guild) ID

1. In Discord: **User Settings → Advanced → Developer Mode** → turn **on**.
2. Right-click your server's icon → **Copy Server ID**.

### 5. Configure the target

Run the GUI:

```
python ban_gui.py
```

Paste in the **bot token** and **server ID**, type the **target handle** (e.g. `someuser`), then click **Resolve & Save target**. It looks the user up, saves their stable ID, and you're set. You can re-open this anytime to change the target.

> You can also paste a raw numeric user ID into the handle field if you already have it.

## Binding the hotkey

The hotkey just needs to run `python ban.py`. Use the full path to both Python and the script. A success/failure desktop notification pops up after each press.

### Windows
- Easiest: install [AutoHotkey](https://www.autohotkey.com/) and create a script:
  ```ahk
  ^!b::Run, pythonw "C:\path\to\ban.py"
  ```
  (`Ctrl+Alt+B` here — change as you like.)
- Or right-click `ban.py` → create a shortcut → Properties → set a **Shortcut key**.

### macOS
- Open **Automator** → new **Quick Action** → add **Run Shell Script**:
  ```
  /usr/bin/python3 "/path/to/ban.py"
  ```
  Save it, then in **System Settings → Keyboard → Keyboard Shortcuts → Services**, assign a shortcut to it.
- Or use a tool like Raycast/BetterTouchTool to bind a key to that command.

### Linux
- Add a custom keyboard shortcut in your desktop settings with the command:
  ```
  python3 /path/to/ban.py
  ```

### Stream Deck / macro keys / other input devices
Set the button's action to "Run program / Open" and point it at the same `python ban.py` command above.

## Notes & safety

- Bans are immediate and bypass the confirmation dialog when triggered via `ban.py` — that's the point of a one-press button. Use the GUI's button if you want a confirm prompt.
- Keep `config.json` private; it holds your bot token.
- If a ban fails, the notification shows why. The most common cause is the bot's role sitting below the target's role — fix the role order (step 3).
