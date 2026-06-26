# Discord Target Keys

A tiny Windows app that lets you **ban, kick, mute, or deafen** a pre-set person on your Discord server with a keyboard shortcut — bound like a game keybind. You pick one target, bind your keys, and moderate them from anywhere. No coding, no setup tools — just download, paste in a token, and pick your keys.

## Download (for most people)

1. Go to the **[Releases](../../releases)** page (or the "Releases" link on the right of this page).
2. Under the latest release, click **DiscordTargetKeys.exe** to download it.
3. Double-click the downloaded file to open the app.

> **Windows may show a blue "Windows protected your PC" warning.** This is normal for small free apps that aren't signed by a big company — it doesn't mean anything is wrong. Click **More info**, then **Run anyway**.

That's it for installing. The first time you open it, follow the in-app **"First-time setup"** button, which walks you through the steps below.

## First-time setup (about 5 minutes, once)

The app has a **First-time setup** button that guides you through this with a link to the right page. Here it is in writing too:

### 1. Create your bot and get a token
- In the app, click **First-time setup → Open Discord Developer Portal** (or go to https://discord.com/developers/applications).
- Click **New Application**, name it anything, then open the **Bot** tab.
- Click **Reset Token**, then **Copy**. Paste it into the app's **Bot token** box.
- On the same page, turn on **Server Members Intent**.

### 2. Add the bot to your server
- Open the **OAuth2 → URL Generator** tab.
- Tick **bot**, then tick the permissions for the actions you want: **Ban Members**, **Kick Members**, **Mute Members**, **Deafen Members**.
- Copy the link at the bottom, open it in your browser, and add the bot to your server.
- In **Server Settings → Roles**, drag the bot's role **above** the people you want to moderate. (A bot can't ban/kick someone whose role sits above its own.)

### 3. Get your Server ID
- In Discord: **User Settings → Advanced → Developer Mode** → turn **on**.
- Right-click your server's icon → **Copy Server ID**. Paste it into the app.

### 4. Pick your target and bind your keys
- Type the person's Discord username into **Target handle**, then click **Resolve & Save target**.
- In the **Actions & hotkeys** table, click **Change bind** next to Ban / Kick / Mute / Deafen and press any key or combination — just like binding a key in a game. Press **Esc** to cancel or **Backspace** to clear a bind.

To change the target later, just type a new username and resolve again.

## The four actions

| Action | What it does | Needs permission |
| --- | --- | --- |
| **Ban** | Removes and blocks them from rejoining | Ban Members |
| **Kick** | Removes them (they can rejoin via invite) | Kick Members |
| **Mute** | Server-mutes them in voice (toggles on/off) | Mute Members |
| **Deafen** | Server-deafens them in voice (toggles on/off) | Deafen Members |

> **Mute and Deafen only work while the target is actually in a voice channel.** If they're not connected, the app tells you so and nothing changes.

## Hotkeys, system tray, and starting with Windows

The app runs quietly in the background:

- **Bind like a game** — click **Change bind**, then press your key or combo. Each action gets its own hotkey, and they fire from anywhere — even with the window closed.
- **Bind almost any key** — letters, numbers, F1–F24, punctuation, numpad keys, and navigation keys all work, with or without Ctrl/Alt/Shift/Win. (You'll get a warning if you bind a plain typing key with no modifier, since it would be captured everywhere.)
- **Instant, no confirmation** — a hotkey runs immediately (that's the point). The on-screen **Run now** buttons ask for confirmation on Ban/Kick if you'd rather click.
- **System tray** — closing the window tucks the app into the tray (next to the clock). Right-click for **Open settings**, **Start with Windows**, and **Quit**. (Quit is the only thing that fully stops it.)
- **Start with Windows** — tick the checkbox (or tray item) and the app launches into the tray each time you log in, so your binds are always ready.

> Hotkeys fire instantly with no confirmation, so pick combos you won't hit by accident. If you ban or kick the wrong person, you can undo it from Discord's **Server Settings → Bans** (or just re-invite a kicked user).

### Mouse buttons, Stream Deck, and macro keys

The app listens for **keyboard** shortcuts. To trigger an action from a mouse side-button, a Stream Deck key, or a macro keypad, use that device's own software to send the keyboard shortcut you bound in the app:

- **Stream Deck** — add a **Hotkey** action to a button and set it to your bound combo (e.g. Ctrl+Alt+B). Pressing the Stream Deck key then fires the action. (You can also use **Open** / **System → Run** to launch the app.)
- **Gaming mice / keyboards** (Logitech G HUB, Razer Synapse, Corsair iCUE, etc.) — bind the extra button to a **keystroke / macro** of your combo.
- **Any macro tool** (AutoHotkey, etc.) — map the input to send the same key combo.

This works with any device that can send a keystroke, so you're not limited to a specific brand.

## Notes & safety

- Your bot token is saved only on your own computer (in your Windows user folder), never uploaded anywhere.
- Keep your bot token private — anyone who has it can control your bot.
- If an action fails, the app tells you why. The most common reasons are the bot's role sitting below the target's role, a missing permission, or (for mute/deafen) the target not being in voice.

---

## For developers / building it yourself

The app is a small Python program; the downloadable `.exe` is built automatically by GitHub Actions on a Windows runner — see `.github/workflows/build-windows.yml`.

Files:
- `ban_gui.py` — the GUI and tray/hotkey app (this is what gets packaged into the `.exe`).
- `ban.py` — small headless ban script (legacy; bans the saved target when run).
- `discord_api.py` — Discord REST API helpers (ban, kick, mute, deafen, handle lookup).
- `config.example.json` — template config; the real `config.json` is gitignored.

Run from source:
```
pip install -r requirements.txt
python ban_gui.py
```

Tests: `python run_tests.py` runs fast smoke tests (no display or Windows needed). These also run automatically on every push via `.github/workflows/ci.yml`. The recommended flow is: push → CI goes green → use the **Actions** tab to run "Build Windows app" manually and test the resulting artifact → only then draft a release.

Build a `.exe` yourself (on Windows):
```
pip install pyinstaller requests pystray pillow
pyinstaller --onefile --windowed --name DiscordTargetKeys --hidden-import=pystray._win32 ban_gui.py
```

Publish a new downloadable build: on GitHub, **Draft a new release**, create a tag like `v0.3.0`, and **Publish**. The workflow builds `DiscordTargetKeys.exe` and attaches it to that release automatically.
