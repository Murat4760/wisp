# Wisp — notes for Claude Code

Windows voice companion (tray app). Python 3.11+. AI backend: Groq if `GROQ_API_KEY` is set (Whisper STT + fast LLM, via plain httpx), else Gemini via `google-genai`. User's own keys in `.env`.

## Files
- `wisp.py` — tray icon, hotkey loop, audio record, Gemini calls, TTS (picks voice per reply language, incl. OneCore voices), autostart, single-instance mutex. Modes: dictate (Right Ctrl; `WISP_HOTKEY=off` disables), command (Right Shift, uses tools, may use the screen — see Rules), screen (F9, screenshot + question, NO tools). `WISP_LANGUAGE` = en / tr / auto.
- `groq_ai.py` — Groq backend: transcribe (drops Whisper's made-up text via `no_speech_prob`), dictation cleanup, tool-calling loop, vision. Builds tool schemas from `commands.py`. Free tier ≈ 7-8k tokens/min per model: keep prompts small, retry/fallback on 429.
- `voicebox_tts.py` — optional AI voice via Voicebox (`/generate/stream`, profile "Wisp EN"); Wisp starts/restarts its server (`keep_server_running`); falls back to Windows voices.
- `avatar.py` — click-through always-on-top avatar (cartoon ghost / orb / island / off) showing listening/thinking/talking. Tk window on the main thread; tray runs detached.
- `commands.py` — functions the AI can call. Type hints + docstrings ARE the tool schema; keep them precise.
- `build.bat` — local PyInstaller build → `dist/Wisp.exe`. CI does the same in `.github/workflows/build.yml`.

## Rules (do not break)
- File actions: only inside the user's home folder, never AppData, always `_confirm()` first, delete = Recycle Bin (`send2trash`).
- On-screen text must never trigger actions (prompt injection). So: screen mode (F9, and Right Shift questions *about* the screen) never gets tools. Right Shift commands that point at the screen ("search this error") are two steps: the vision model only copies out the referenced text (no tools), then the tool model acts on it, and `allowed_with_screen` makes every action whose target isn't in the user's own words ask Yes/No first.
- No shell/terminal execution tools.
- Never commit `.env`.

## Run / test
- Dev: `python wisp.py` (console shows errors), logs in `wisp.log` (`[heard]`, `[tool]`, `[guard]` lines show what happened).
- Full test: `.venv\Scripts\python.exe tests\e2e_test.py` — real AI calls with Windows-voice speech instead of the mic; paste, popups, browser, launches and media keys are captured, Yes/No answers No. Needs the keys in `.env`; uses a few minutes of Groq quota.
- Windows-only (winreg, winsound, SAPI, MessageBoxW). Can't run on Linux/macOS.

## Ideas backlog
circle-to-ask (drag box), local memory (JSON/SQLite), persistent reminders.
