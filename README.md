# Wisp v3 — voice companion for Windows (tray app)

| Hold | Does |
|---|---|
| **Right Ctrl** | Dictate. Clean text is pasted at your cursor. Turn it off with `WISP_HOTKEY=off` in `.env`. |
| **Right Shift** | Voice command or question, with a spoken reply. Can use what's on your screen: "search this error", "open the link here". |
| **F9** | Ask about your screen. Spoken answer + popup. |

Command examples: "Open Brave", "open task manager", "open downloads", "search Tailwind grid docs", "go to github.com", "next song", "volume up", "remind me in 20 minutes to call Can Bey", "suggest a video to watch", "search this error", "move invoice.pdf from downloads to documents", "rename the file called logo final to logo.png", "delete screenshot 123".

Language: English by default. `WISP_LANGUAGE=tr` for Turkish only, `auto` for English / Turkish / Azerbaijani (mixed ok).

Beeps: high = dictation, mid = command, highest = screen, low = sent, very low = error (see log).

## Setup (once)
1. Install Python 3.11+ from python.org (tick "Add to PATH").
2. Get a free key. **Groq is recommended** (much faster, great Turkish/Azerbaijani speech recognition): https://console.groq.com/keys. Gemini also works: https://aistudio.google.com/api-keys
3. In this folder:
   ```
   pip install -r requirements.txt
   copy .env.example .env
   ```
4. Open `.env`, paste your key into `GROQ_API_KEY` (or `GEMINI_API_KEY`).

A little cartoon ghost (bottom-right) shows what Wisp is doing: listening (sound waves), thinking (thought bubbles), talking, done (waves, sparkles), error (dizzy). Tray menu → **Avatar** switches to a glowing orb, a top-of-screen "island" pill that shows the text, or off.

**Nicer voice (optional):** install [Voicebox](https://github.com/jamiepine/voicebox) and create a voice profile named `Wisp EN` (e.g. a Kokoro preset voice). Wisp starts Voicebox's server by itself; without it, Windows voices are used.

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
- Text on your screen can't make Wisp do anything: F9 has no actions at all, and when Right Shift uses the screen ("open the link here"), any action whose target came from the screen rather than your own words shows a Yes/No popup first.
- No terminal commands, ever.

## Notes
- Your audio, and screenshots (F9, or Right Shift when your words point at the screen), go to the AI provider (Groq or Google). Free tiers may review them. Don't use the screen features with client data or passwords visible.
- Right Shift only sends a screenshot when your words point at the screen ("this", "that", "here", "link", "error"…); "open Brave" sends none.
- Without Voicebox, spoken replies use your Windows voice. For a Turkish voice: Settings > Time & language > Speech > Add voices.
- Won't paste or click into apps running as Administrator unless Wisp is too.
- F9 conflicts with VS Code's debugger. Change it with `WISP_SCREEN_HOTKEY` in `.env`.
- Reminders are lost if Wisp restarts.
- Screen mode reads your primary monitor only.
