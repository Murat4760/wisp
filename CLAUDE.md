# Wisp — notes for Claude Code

Windows voice companion (tray app). Python 3.11+, Gemini via `google-genai`, user's own key in `.env`.

## Files
- `wisp.py` — tray icon, hotkey loop, audio record, Gemini calls, TTS, autostart. Modes: dictate (Right Ctrl), command (Right Shift, uses tools), screen (F9, screenshot + question, NO tools).
- `commands.py` — functions Gemini can call. Type hints + docstrings ARE the tool schema; keep them precise.
- `build.bat` — local PyInstaller build → `dist/Wisp.exe`. CI does the same in `.github/workflows/build.yml`.

## Rules (do not break)
- File actions: only inside the user's home folder, never AppData, always `_confirm()` first, delete = Recycle Bin (`send2trash`).
- Screen mode must never get tools (prompt-injection from on-screen text).
- No shell/terminal execution tools.
- Never commit `.env`.

## Run / test
- Dev: `python wisp.py` (console shows errors), logs in `wisp.log`.
- Windows-only (winreg, winsound, SAPI, MessageBoxW). Can't run on Linux/macOS.

## Ideas backlog
circle-to-ask (drag box), local memory (JSON/SQLite), persistent reminders, island UI.
