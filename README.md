# Wisp v3 — voice companion for Windows (tray app)

| Hold | Does |
|---|---|
| **Right Ctrl** | Dictate. Clean text is pasted at your cursor (EN / TR / AZ, mixed ok). |
| **Right Shift** | Voice command, with a spoken reply. |
| **F9** | Ask about your screen. Spoken answer + popup. |

Command examples: "Open Spotify", "Spotify'ı aç", "open downloads", "search Tailwind grid docs", "go to vercel.com", "next song", "volume up", "remind me in 20 minutes to call Can Bey", "move invoice.pdf from downloads to documents", "rename the file called logo-final to logo.png", "delete screenshot 123".

Beeps: high = dictation, mid = command, highest = screen, low = sent, very low = error (see log).

## Setup (once)
1. Install Python 3.11+ from python.org (tick "Add to PATH").
2. Get a free key: https://aistudio.google.com/api-keys
3. In this folder:
   ```
   pip install -r requirements.txt
   copy .env.example .env
   ```
4. Open `.env`, paste your key.

## Run
```
pythonw wisp.py
```
A blue dot appears in the tray. Right-click it for: Voice replies, Start with Windows, Open log, Quit.
First time, use `python wisp.py` instead so you see any startup errors.

## Build Wisp.exe (no Python needed afterwards)
1. Do Setup steps 1–4 once.
2. Double-click `build.bat`. Wait 1–2 minutes.
3. Your app is `dist\Wisp.exe`. Keep `.env` in the same folder as it.
4. You can now move the `dist` folder anywhere (e.g. `C:\Apps\Wisp`) and delete the rest. Right-click the tray dot → **Start with Windows**.

If Windows Defender / SmartScreen flags it: that's common for unsigned PyInstaller apps that hook the keyboard. It's your own code, so "More info → Run anyway" is fine. Don't send this .exe to others; they'd get scary warnings too.

## Safety
- File actions only touch files inside your user folder (never AppData), always show a Yes/No popup, and delete goes to the Recycle Bin.
- Screen mode has no tools on purpose, so text on your screen can't make Wisp do anything.
- No terminal commands, ever.

## Notes
- Free-tier audio **and screenshots** may be reviewed by Google. Don't use F9 with client data or passwords on screen.
- Spoken replies use your Windows voice. For a Turkish voice: Settings > Time & language > Speech > Add voices.
- Won't paste or click into apps running as Administrator unless Wisp is too.
- F9 conflicts with VS Code's debugger. Change it with `WISP_SCREEN_HOTKEY` in `.env`.
- Reminders are lost if Wisp restarts.
- Screen mode reads your primary monitor only.
