"""Optional nicer voice via Voicebox (github.com/jamiepine/voicebox), a local AI voice app.
If its server is running and has the named voice profiles, replies are spoken with them; otherwise
wisp.py falls back to the Windows voices. Voicebox has no Azerbaijani: wisp.py sends that as Turkish."""
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx

# Voicebox engine per language: Chatterbox Multilingual is its only engine that speaks Turkish.
ENGINE = {"tr": "chatterbox"}


def start_server(log):
    """Start Voicebox's server in the background if it's installed but not running, so Wisp's
    'Start with Windows' covers it too and the Voicebox window never needs to be open."""
    port = int(os.getenv("WISP_VOICEBOX_URL", "http://127.0.0.1:17493").rsplit(":", 1)[1])
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return _note(log, "running")  # already running (Wisp's earlier start or the Voicebox app)
    local, roaming = Path(os.environ["LOCALAPPDATA"]), Path(os.environ["APPDATA"])
    exe = Path(os.getenv("WISP_VOICEBOX_SERVER", local / "Voicebox" / "voicebox-server.exe"))
    if not exe.is_file():
        return _note(log, f"not installed ({exe})")  # Windows voices are used
    out = open(exe.parent / "server-wisp.log", "ab")
    # same data folder as the Voicebox app, so its voice profiles are shared; no window, outlives Wisp
    subprocess.Popen([str(exe), "--data-dir", str(roaming / "sh.voicebox.app"), "--port", str(port)],
                     cwd=exe.parent, stdout=out, stderr=out,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    _note(log, "starting")
    log(f"[voice] started Voicebox server: {exe}")


_last_state = None


def _note(log, state):
    """Log the Voicebox server state only when it changes (this is checked every minute)."""
    global _last_state
    if state != _last_state:
        _last_state = state
        log(f"[voice] Voicebox server: {state}")


def keep_server_running(log, every=60):
    """Start the server now, and again whenever it stops (e.g. killed along with whatever launched it)."""
    while True:
        try:
            start_server(log)
        except Exception as e:
            log(f"[voice] couldn't start Voicebox server: {e}")
        time.sleep(every)


class Voicebox:
    def __init__(self):
        self.url = os.getenv("WISP_VOICEBOX_URL", "http://127.0.0.1:17493")
        self.names = {"en": os.getenv("WISP_VOICEBOX_EN", "Wisp EN"), "tr": os.getenv("WISP_VOICEBOX_TR", "Wisp TR")}
        self.http = httpx.Client(base_url=self.url, timeout=90)  # first use loads the model onto the GPU
        self.profiles, self.checked = {}, 0.0

    def _profiles(self):
        """{lang: profile}, re-checked at most every 30s so starting Voicebox later just works."""
        if time.time() - self.checked > 30:
            self.checked = time.time()
            try:
                by_name = {p["name"].lower(): p for p in self.http.get("/profiles", timeout=0.5).json()}
                self.profiles = {lang: by_name[n.lower()] for lang, n in self.names.items() if n.lower() in by_name}
            except Exception:
                self.profiles = {}  # not running (keep_server_running restarts it)
        return self.profiles

    def wav(self, text, lang):
        """WAV bytes for text in 'en' or 'tr', or None if Voicebox can't do it right now."""
        p = self._profiles().get(lang)
        if not p:
            return None
        # Always send the engine: Voicebox 0.5.0 defaults a missing one to "qwen", not the profile's own.
        engine = ENGINE.get(lang) or p.get("default_engine") or p.get("preset_engine") or "qwen"
        body = {"text": text, "profile_id": p["id"], "language": lang, "engine": engine}
        r = self.http.post("/generate/stream", json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Voicebox {r.status_code}: {r.text[:200]}")
        return r.content
