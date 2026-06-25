# Discord Ban Script

A tiny Windows app that bans one pre-set person from your Discord server with a single click. No coding, no setup tools — just download, paste in a token, and you're done.

## Download (for most people)

1. Go to the **[Releases](../../releases)** page (or the "Releases" link on the right of this page).
2. Under the latest release, click **DiscordBanScript.exe** to download it.
3. Double-click the downloaded file to open the app.

> **Windows may show a blue "Windows protected your PC" warning.** This is normal for small free apps that aren't signed by a big company — it doesn't mean anything is wrong. Click **More info**, then **Run anyway**.

That's it for installing. The first time you open it, follow the in-app **"First-time setup"** button, which walks you through the steps below.

## First-time setup (about 5 minutes, once)

This is the only slightly fiddly part, and the app has a **First-time setup** button that guides you through it with a link to the right page. Here it is in writing too:

### 1. Create your bot and get a token
- In the app, click **First-time setup → Open Discord Developer Portal** (or go to https://discord.com/developers/applications).
- Click **New Application**, name it anything, then open the **Bot** tab.
- Click **Reset Token**, then **Copy**. Paste it into the app's **Bot token** box.
- On the same page, turn on **Server Members Intent**.

### 2. Add the bot to your server
- Open the **OAuth2 → URL Generator** tab.
- Tick **bot**, then tick **Ban Members**.
- Copy the link at the bottom, open it in your browser, and add the bot to your server.
- In **Server Settings → Roles**, drag the bot's role **above** the people you want to be able to ban. (A bot can't ban someone whose role sits above its own.)

### 3. Get your Server ID
- In Discord: **User Settings → Advanced → Developer Mode** → turn **on**.
- Right-click your server's icon → **Copy Server ID**. Paste it into the app.

### 4. Pick who gets banned
- Type the person's Discord username into **Target handle**.
- Click **Resolve & Save target**. The app looks them up and remembers them.

Now whenever you click **BAN TARGET NOW**, that person is banned. To change the target later, just type a new username and resolve again.

## Hotkey, system tray, and starting with Windows

The app is built to run quietly in the background:

- **System tray** — closing the window doesn't quit the app; it tucks it into the system tray (next to the clock). Right-click the tray icon for **Open settings**, **Ban now**, **Start with Windows**, and **Quit**. (Quit is the only thing that fully stops it.)
- **Ban hotkey** — press **Ctrl+Alt+B** (the default) anywhere to instantly ban your target, even when the window is closed. No popup, no confirmation — that's the point. Change the combo with the **Change…** button under "Background & hotkey".
- **Start with Windows** — tick the **Start with Windows** checkbox (or the tray menu item) and the app launches into the tray automatically each time you log in, so the hotkey is always ready. Untick it to stop.

> Because the hotkey bans instantly with no confirmation, pick a combo you won't hit by accident. If you ever ban the wrong person, you can unban them from Discord's **Server Settings → Bans**.

## Notes & safety

- Your bot token is saved only on your own computer (in your Windows user folder), never uploaded anywhere.
- Keep your bot token private — anyone who has it can control your bot.
- If a ban fails, the app tells you why. The most common reason is the bot's role sitting below the target's role — fix the role order in step 2.

---

## For developers / building it yourself

The app is a small Python program; the downloadable `.exe` is built automatically by GitHub Actions on a Windows runner — see `.github/workflows/build-windows.yml`.

Files:
- `ban_gui.py` — the GUI (this is what gets packaged into the `.exe`).
- `ban.py` — headless instant-ban script for binding to a hotkey.
- `discord_api.py` — shared Discord REST API helpers (ban + handle lookup).
- `config.example.json` — template config; the real `config.json` is gitignored.

Run from source:
```
pip install -r requirements.txt
python ban_gui.py
```

Build a `.exe` yourself (on Windows):
```
pip install pyinstaller requests
pyinstaller --onefile --windowed --name DiscordBanScript ban_gui.py
```

Publish a new downloadable build: on GitHub, **Draft a new release**, create a tag like `v1.0`, and **Publish**. The workflow builds `DiscordBanScript.exe` and attaches it to that release automatically.
