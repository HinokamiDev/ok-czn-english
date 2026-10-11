"""Write what a run is doing to one JSON file, for an assistant watching from outside the app.

HinokamiDev fork. A watcher (GPT) reads this file instead of touching the game or the app window. `durum` is
the current state: calisiyor (running), takildi (stuck on one screen), hata (stopped on an error) or durdu
(stopped). `guncelleme` is refreshed while frames are being handled, at most every HEARTBEAT_SECONDS, so a
value that stops moving means the app closed or froze. Writing the file never stops a run.
"""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from ok import Logger

logger = Logger.get_logger(__name__)

SCHEMA = "ok-czn-hd-durum-v1"
# %LOCALAPPDATA%\ok-czn-hd on Windows, so a watcher finds it without knowing where the app is installed.
PATH = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "ok-czn-hd" / "son-calisma.json"
HEARTBEAT_SECONDS = 10
MAX_EVENTS = 50

# Event -> the state it leaves the run in.
STATES = {"basladi": "calisiyor", "kosu_bitti": "calisiyor", "takildi": "takildi", "hata": "hata", "durdu": "durdu",
          # A choice handed to a watcher through `src/en/ask.py`, and the run carrying on once it is answered.
          "karar": "karar_bekliyor", "karar_verildi": "calisiyor"}

_last_beat = 0.0


def _now():
    return datetime.now().isoformat(timespec="seconds")


def read(path=None):
    """The status as last written, or None when there is none or it cannot be parsed."""
    try:
        return json.loads(Path(path or PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _score(task):
    counters = getattr(task, "node_status", None) or {}
    return {"tur": counters.get("total_rounds", 0), "basarili": counters.get("success_rounds", 0)}


def event(task, kind, message, path=None):
    """Record one event and the state it leaves the run in.

    Args:
        task: The mode the event belongs to.
        kind: One of STATES.
        message: A short English line, the same one the notification shows.
        path: Where to write, PATH unless a test says otherwise.
    """
    global _last_beat
    path = path or PATH
    try:
        data = read(path) or {}
        now = _now()
        if kind == "basladi" or data.get("sema") != SCHEMA:
            data = {"sema": SCHEMA, "baslangic": now, "olaylar": []}
        state = STATES[kind]
        # A stop that follows an error is the executor cleaning up; the error is what the watcher needs.
        if kind == "durdu" and data.get("durum") == "hata":
            state = "hata"
        data.update(mod=getattr(task, "name", ""), durum=state, son_olay=kind, mesaj=message, guncelleme=now,
                    **_score(task))
        data["olaylar"] = (data.get("olaylar") or [])[-(MAX_EVENTS - 1):] + [
            {"zaman": now, "olay": kind, "mesaj": message}]
        _write(data, path)
        _last_beat = time.monotonic()
    except Exception as error:
        logger.warning(f"could not write the run status: {error}")


def heartbeat(task, path=None, every=HEARTBEAT_SECONDS):
    """Show the run is still alive, without adding an event."""
    global _last_beat
    if time.monotonic() - _last_beat < every:
        return
    _last_beat = time.monotonic()
    path = path or PATH
    try:
        data = read(path)
        if not data or data.get("durum") not in ("calisiyor", "takildi", "karar_bekliyor"):
            return
        data.update(guncelleme=_now(), **_score(task))
        _write(data, path)
    except Exception as error:
        logger.warning(f"could not refresh the run status: {error}")


def recovered(task, path=None):
    """Clear a stuck state once the screen is moving again."""
    data = read(path or PATH)
    if data and data.get("durum") == "takildi":
        data.update(durum="calisiyor", guncelleme=_now(), **_score(task))
        try:
            _write(data, path or PATH)
        except Exception as error:
            logger.warning(f"could not clear the stuck status: {error}")


CONTROL_FLOW = ("TaskDisabledException", "FinishedException")


def watching(original, task, path=None):
    """Wrap a mode's per-frame `run` to keep the heartbeat going and record an error that stops it."""
    def run(*args, **kwargs):
        heartbeat(task, path)
        try:
            result = original(*args, **kwargs)
        except Exception as error:
            if type(error).__name__ not in CONTROL_FLOW:
                event(task, "hata", f"Stopped on an error: {error!r}"[:300], path)
            raise
        # Imported here: the snapshot module records its finding through this one.
        from src.en.snapshot import checking
        checking(task)
        return result

    return run


def stopping(original, task, path=None):
    """Wrap a mode's `disable` so a stop is recorded."""
    def disable(*args, **kwargs):
        result = original(*args, **kwargs)
        event(task, "durdu", "Run stopped.", path)
        return result

    return disable
