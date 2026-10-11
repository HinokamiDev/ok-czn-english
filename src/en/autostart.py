"""Start a mode by itself once the app has opened, when a watcher asked for it.

A fix that needs a restart used to end the run there: the app came back with every mode stopped, and someone had to
press Start again. The supervisor (`GOZETMEN.ps1`) writes `otomatik-baslat.json` beside the status file before it
restarts the app, naming the mode that was running; once the window is up this starts that mode the way its Start
button does, and removes the file, so it happens once per request and never on an ordinary launch.
"""

import json
import os
import subprocess
import threading
import time

from ok import Logger

from src.en import status

logger = Logger.get_logger(__name__)

FILE_NAME = "otomatik-baslat.json"
# A running mode can hand over to another without a restart: it writes the mode wanted to `SWITCH_NAME`, and the
# window's timer stops whatever runs and starts that one. `RETURN_NAME` asks for the Story mode to be started again
# once nothing is running any more - how a Story chaos stage goes to the Chaos mode and comes back after its run.
SWITCH_NAME = "mod-degistir.json"
RETURN_NAME = "story-donus.json"
POLL_MS = 2000
# Restarting the game itself, for when it freezes. The app runs elevated, as the game and STOVE do, so it can close
# the game and have STOVE start it again without a UAC prompt nobody may be there to answer. Only the game's own
# process is touched, and it is started again the way the desktop shortcut does it.
GAME_RESTART_NAME = "oyun-yeniden.istek"
GAME_PROCESS = "ssr-stove-shield.exe"
GAME_URL = "sgup://run/STOVE_CHAOSZERO?auto_action=PrepareAndLaunch"
GAME_CLOSE_SECONDS = 15
_timer = None
# Long enough for the game window to be found and connected, as it is when someone presses Start by hand.
DELAY_MS = 10000
# The class names the request may name, and the Chinese task names the status file records them under.
MODES = {"ChaosMode": "自动卡厄思模式", "SortieMode": "自动出击模式", "StoryMode": "半自动剧情模式"}


def request_path():
    return status.PATH.parent / FILE_NAME


def request_switch(mode, then_story=False):
    """Ask the window to stop the running mode and start another.

    Args:
        mode: The class name of the mode to start.
        then_story: Start the Story mode again once that mode has stopped.
    """
    folder = status.PATH.parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SWITCH_NAME).write_text(json.dumps({"mod": mode}), encoding="utf-8")
    if then_story:
        write_return(mode)


def write_return(after, seen=False):
    """Ask for the Story mode once `after` has run and stopped.

    Args:
        after: The class name of the mode whose run has to end first.
        seen: Whether that mode has been seen running yet. Until it has, nothing running means it has not started,
            not that it is done - the first version returned to Story the moment the app opened, before the Chaos
            mode it was waiting on had even begun.
    """
    folder = status.PATH.parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / RETURN_NAME).write_text(json.dumps({"mod": "StoryMode", "after": after, "seen": seen}),
                                      encoding="utf-8")


def take_request(path=None):
    """Read and remove the start request.

    Returns:
        The mode's class name, or None when there is no valid request.
    """
    path = path or request_path()
    if not path.exists():
        return None
    try:
        # utf-8-sig: Windows PowerShell 5.1 writes a byte-order mark ahead of UTF-8, which plain utf-8 refuses.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        logger.warning(f"ignoring an unreadable start request: {error}")
        data = {}
    finally:
        path.unlink(missing_ok=True)
    wanted = data.get("mod") if isinstance(data, dict) else None
    for class_name, task_name in MODES.items():
        if wanted in (class_name, task_name):
            return class_name
    if wanted:
        logger.warning(f"ignoring a start request for an unknown mode {wanted!r}")
    return None


def start_requested(executor, start_controller):
    """Start the requested mode, if there is a request.

    Args:
        executor: The task executor holding the modes.
        start_controller: The controller the Start button calls.

    Returns:
        The mode started, or None.
    """
    class_name = take_request()
    if class_name is None:
        return None
    task = next((task for task in executor.get_all_tasks() if task.__class__.__name__ == class_name), None)
    if task is None:
        logger.warning(f"start request for {class_name}, which is not loaded")
        return None
    logger.info(f"starting {class_name} on request, as its Start button would")
    start_controller.start(task)
    return task


def game_running():
    found = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_PROCESS}", "/NH"], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return GAME_PROCESS.lower() in (found.stdout or "").lower()


def restart_game():
    """Close the game, politely first, and start it again through STOVE."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(["taskkill", "/IM", GAME_PROCESS], capture_output=True, creationflags=flags)
    for _ in range(GAME_CLOSE_SECONDS):
        if not game_running():
            break
        time.sleep(1)
    forced = game_running()
    if forced:
        subprocess.run(["taskkill", "/IM", GAME_PROCESS, "/T", "/F"], capture_output=True, creationflags=flags)
        time.sleep(3)
    logger.info(f"game closed{' by force' if forced else ''}, starting it again through STOVE")
    os.startfile(GAME_URL)


def take_game_restart():
    """Start a game restart in the background when one was asked for, so the window's timer is not held up."""
    path = status.PATH.parent / GAME_RESTART_NAME
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    threading.Thread(target=restart_game, name="game-restart", daemon=True).start()
    return True


def running(executor):
    return [task for task in executor.get_all_tasks()
            if task.__class__.__name__ in MODES and getattr(task, "enabled", False)]


def due_return(executor, path):
    """Say whether the return to the Story mode is due, keeping track of the run it waits on.

    Returns:
        "StoryMode" once the awaited mode has run and nothing runs any more, otherwise None.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return None
    after = data.get("after")
    names = [task.__class__.__name__ for task in running(executor)]
    if after in names:
        if not data.get("seen"):
            write_return(after, seen=True)
        return None
    if names or not data.get("seen"):
        return None
    path.unlink(missing_ok=True)
    return "StoryMode"


def poll(executor, start_controller):
    """Carry out a requested hand-over, or the return to the Story mode once nothing runs.

    Returns:
        The mode started, or None.
    """
    folder = status.PATH.parent
    wanted = take_request(folder / SWITCH_NAME)
    # A supervisor restart's own start request goes first: restarted into the Chaos mode mid-run, the app found nothing
    # running and the return marker already "seen", went back to Story at once, and Story faced the Chaos run's reward
    # screen (12 Oct, 00:51).
    if wanted is None and request_path().exists():
        return None
    if wanted is None:
        wanted = due_return(executor, folder / RETURN_NAME)
        if wanted is None:
            return None
    task = next((task for task in executor.get_all_tasks() if task.__class__.__name__ == wanted), None)
    if task is None:
        return None
    for other in running(executor):
        if other is not task:
            logger.info(f"stopping {other.__class__.__name__} to hand over to {wanted}")
            other.disable()
    logger.info(f"starting {wanted} on a hand-over request")
    start_controller.start(task)
    return task


def schedule():
    """Arrange for the request to be honoured once the window has had time to connect to the game."""
    try:
        from PySide6.QtCore import QTimer
        from ok import og
    except ImportError as error:
        logger.warning(f"could not schedule the start request: {error}")
        return

    def run():
        try:
            start_requested(og.executor, og.app.start_controller)
        except Exception as error:
            logger.error(f"could not start the requested mode: {error}", exception=error)

    QTimer.singleShot(DELAY_MS, run)

    def polling():
        try:
            take_game_restart()
            poll(og.executor, og.app.start_controller)
        except Exception as error:
            logger.error(f"could not carry out a mode hand-over: {error}", exception=error)

    global _timer
    _timer = QTimer()
    _timer.timeout.connect(polling)
    _timer.start(POLL_MS)
