"""Wisp tools. Gemini picks and calls these.
Safety: file actions only touch files inside your user folder (not AppData), always ask yes/no first,
and delete goes to the Recycle Bin. Nothing runs shell input."""
import ctypes
import difflib
import json
import os
import shutil
import subprocess
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import keyboard
from send2trash import send2trash

HOME = Path.home()
KNOWN = ["desktop", "downloads", "documents", "pictures", "videos", "music"]
_apps = None  # cached {lowercase name: AppID}
_titles = {}  # {lowercase name: name as Windows shows it}, for replies ("Opened Brave.")


# ---------- helpers (not exposed to Gemini) ----------
def popup(text, title="Wisp"):
    """Non-blocking info popup."""
    threading.Thread(target=ctypes.windll.user32.MessageBoxW,
                     args=(0, text, title, 0x40 | 0x1000), daemon=True).start()


def _confirm(text):
    """Blocking Yes/No popup. True only if the user clicks Yes."""
    return ctypes.windll.user32.MessageBoxW(0, text, "Wisp - confirm", 0x4 | 0x20 | 0x1000) == 6


def _folder(name):
    """Resolve 'downloads' etc. (incl. OneDrive-redirected) or a path; None if not a folder."""
    key = name.lower().strip()
    if key in KNOWN:
        for p in (HOME / key.capitalize(), HOME / "OneDrive" / key.capitalize()):
            if p.is_dir():
                return p
        return None
    p = Path(name).expanduser()
    return p if p.is_dir() else None


def _safe_file(path):
    """Only existing files inside the user folder, never AppData."""
    p = Path(path).expanduser().resolve()
    if not p.is_file() or not p.is_relative_to(HOME) or "AppData" in p.parts:
        return None
    return p


def _squash(name):
    """Lowercase, letters/digits only: a spoken 'logo final' must find 'logo-final.png' / 'logo_final.png'."""
    return "".join(c for c in name.lower() if c.isalnum())


def _load_apps():
    global _apps
    if not _apps:  # also retry if an earlier load came back empty
        # Force UTF-8 both ways: with the console's own code page, non-English app names
        # (e.g. Turkish "Görev Yöneticisi") failed to decode and the whole list came back empty.
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json"],
            capture_output=True, encoding="utf-8", errors="replace", creationflags=0x08000000,  # no window
        ).stdout
        data = json.loads(out or "[]")
        data = data if isinstance(data, list) else [data]
        _apps = {a["Name"].lower(): a["AppID"] for a in data}
        _titles.update({a["Name"].lower(): a["Name"] for a in data})
    return _apps


def app_names(heard=None, limit=12):
    """Installed app names, so the AI can map a misheard name ('I'm brave') to a real app ('Brave').
    With `heard`, only the `limit` names that sound closest to it (keeps the AI request small)."""
    skip = ("uninstall", "documentation", "release notes", "readme", "website", "manual", "faq", "yardım")
    names = [n for n in _load_apps() if not any(s in n for s in skip)]
    # + English names of Windows tools (open_app maps them to Turkish ones), so "task manager" is offered
    names += [k for k, v in WINDOWS_TR.items() if v in _load_apps()]
    if heard is None:
        return sorted(names)
    words = "".join(c if c.isalnum() else " " for c in heard.lower()).split()
    grams = {" ".join(words[i:i + k]) for k in (1, 2, 3) for i in range(len(words))}

    def score(name):
        return max((difflib.SequenceMatcher(None, name, g).ratio() for g in grams), default=0)

    return sorted(names, key=score, reverse=True)[:limit]


# ---------- tools ----------
# English names of built-in Windows tools -> their names on a Turkish Windows (Start menu shows these)
WINDOWS_TR = {k: v.lower() for k, v in {  # .lower() like the app list does ("İ" -> "i" + combining dot)
    "task manager": "Görev Yöneticisi", "settings": "Ayarlar", "control panel": "Denetim Masası",
    "file explorer": "Dosya Gezgini", "explorer": "Dosya Gezgini", "command prompt": "Komut İstemi",
    "cmd": "Komut İstemi", "registry editor": "Kayıt Defteri Düzenleyicisi", "run": "Çalıştır",
    "on-screen keyboard": "Ekran Klavyesi", "system information": "Sistem Bilgisi", "services": "Hizmetler",
    "event viewer": "Olay Görüntüleyicisi", "disk cleanup": "Disk Temizleme", "magnifier": "Büyüteç",
    "narrator": "Ekran Okuyucusu", "character map": "Karakter Eşlem", "task scheduler": "Görev Zamanlayıcı",
    "resource monitor": "Kaynak İzleyicisi", "performance monitor": "Performans İzleyicisi",
    "remote desktop": "Uzak Masaüstü Bağlantısı", "steps recorder": "Adım Kaydedicisi",
    "computer management": "Bilgisayar Yönetimi", "windows tools": "Windows Araçları",
}.items()}


def open_app(name: str) -> str:
    """Open an installed Windows app by its name, e.g. 'Spotify', 'Chrome', 'Notepad', 'WhatsApp'."""
    apps = _load_apps()
    q = name.lower().strip()
    # exact name, then the Turkish-Windows name of a built-in tool, then partial match ('settings' must
    # open Ayarlar, not 'WSL Settings')
    matches = ([n for n in apps if n in (q, WINDOWS_TR.get(q))]
               or sorted((n for n in apps if q in n), key=len))
    if not matches:
        return f"No installed app matches '{name}'."
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{apps[matches[0]]}"])
    return f"Opened {_titles.get(matches[0], matches[0])}."


def open_website(url: str) -> str:
    """Open a website in the default browser. Use a full https URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    site = urllib.parse.urlparse(url).netloc.removeprefix("www.") or url  # reply is spoken: "youtube.com"
    return f"Opened {site}."


def search_web(query: str) -> str:
    """Search Google for a query in the default browser."""
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    return f"Searched for '{query}'."


def open_folder(folder: str) -> str:
    """Open a folder in File Explorer: 'downloads', 'documents', 'desktop', 'pictures', 'videos', 'music', or a full path."""
    path = _folder(folder)
    if not path:
        return f"Folder not found: {folder}"
    os.startfile(path)
    return f"Opened {path}."


def media(action: str) -> str:
    """Control media/volume. action is one of: play_pause, next, previous, volume_up, volume_down, mute."""
    keys = {"play_pause": "play/pause media", "next": "next track", "previous": "previous track",
            "volume_up": "volume up", "volume_down": "volume down", "mute": "volume mute"}
    if action not in keys:
        return f"Unknown media action: {action}"
    presses = 5 if action in ("volume_up", "volume_down") else 1
    for _ in range(presses):
        keyboard.send(keys[action])
    said = {"play_pause": "Toggled play and pause", "next": "Skipped to the next track",
            "previous": "Went back a track", "volume_up": "Turned the volume up",
            "volume_down": "Turned the volume down", "mute": "Toggled mute"}
    return f"{said[action]}."  # spoken as-is, so no 'volume_up'


def set_reminder(minutes: float, message: str) -> str:
    """Show a popup reminder after the given number of minutes (only while Wisp keeps running)."""
    threading.Timer(minutes * 60, popup, args=(message, "Wisp reminder")).start()
    return f"Okay, I'll remind you in {minutes:g} minute{'' if minutes == 1 else 's'}: {message}."


def find_files(name: str) -> str:
    """Find files whose name contains `name` in Desktop, Downloads, Documents, Pictures, Videos, Music.
    Returns up to 10 full paths. Use this before moving, renaming or deleting a file."""
    q, hits = _squash(name), []
    if not q:
        return f"No files matching '{name}'."
    for key in KNOWN:
        root = _folder(key)
        if not root:
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if len(Path(dirpath).relative_to(root).parts) >= 3:
                dirnames.clear()  # max 3 levels deep
            hits += [str(Path(dirpath) / f) for f in filenames if q in _squash(f)]
            if len(hits) >= 10:
                return "\n".join(hits[:10])
    return "\n".join(hits) or f"No files matching '{name}'."


def move_file(path: str, destination_folder: str) -> str:
    """Move a file (full path from find_files) to a folder ('downloads', 'documents', ... or a full path). Asks the user first."""
    src, dest = _safe_file(path), _folder(destination_folder)
    if not src:
        return "Refused: file not found or outside your user folder."
    if not dest:
        return f"Folder not found: {destination_folder}"
    target = dest / src.name
    if target.exists():
        return f"Refused: {target} already exists."
    if not _confirm(f"Move\n{src}\nto\n{dest}?"):
        return "Cancelled, nothing was changed."
    shutil.move(str(src), str(target))
    return f"Moved to {target}."


def rename_file(path: str, new_name: str) -> str:
    """Rename a file (full path from find_files). new_name is just the file name, e.g. 'invoice.pdf'. Asks the user first."""
    src = _safe_file(path)
    if not src:
        return "Refused: file not found or outside your user folder."
    if any(c in new_name for c in '\\/:*?"<>|'):
        return "Refused: invalid file name."
    target = src.with_name(new_name)
    if target.exists():
        return f"Refused: {target.name} already exists."
    if not _confirm(f"Rename\n{src.name}\nto\n{new_name}?"):
        return "Cancelled, nothing was changed."
    src.rename(target)
    return f"Renamed to {new_name}."


def delete_file(path: str) -> str:
    """Send a file (full path from find_files) to the Recycle Bin. Asks the user first."""
    src = _safe_file(path)
    if not src:
        return "Refused: file not found or outside your user folder."
    if not _confirm(f"Send to Recycle Bin?\n{src}"):
        return "Cancelled, nothing was changed."
    send2trash(str(src))
    return f"Sent {src.name} to the Recycle Bin."


TOOLS = [open_app, open_website, search_web, open_folder, media, set_reminder,
         find_files, move_file, rename_file, delete_file]
