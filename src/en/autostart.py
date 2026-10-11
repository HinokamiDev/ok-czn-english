"""Start a mode by itself once the app has opened, when a watcher asked for it.

A fix that needs a restart used to end the run there: the app came back with every mode stopped, and someone had to
press Start again. The supervisor (`GOZETMEN.ps1`) writes `otomatik-baslat.json` beside the status file before it
restarts the app, naming the mode that was running; once the window is up this starts that mode the way its Start
button does, and removes the file, so it happens once per request and never on an ordinary launch.
"""

import json

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
        (folder / RETURN_NAME).write_text(json.dumps({"mod": "StoryMode"}), encoding="utf-8")


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


def running(executor):
    return [task for task in executor.get_all_tasks()
            if task.__class__.__name__ in MODES and getattr(task, "enabled", False)]


def poll(executor, start_controller):
    """Carry out a requested hand-over, or the return to the Story mode once nothing runs.

    Returns:
        The mode started, or None.
    """
    folder = status.PATH.parent
    wanted = take_request(folder / SWITCH_NAME)
    if wanted is None:
        if not (folder / RETURN_NAME).exists() or running(executor):
            return None
        wanted = take_request(folder / RETURN_NAME)
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
            poll(og.executor, og.app.start_controller)
        except Exception as error:
            logger.error(f"could not carry out a mode hand-over: {error}", exception=error)

    global _timer
    _timer = QTimer()
    _timer.timeout.connect(polling)
    _timer.start(POLL_MS)
