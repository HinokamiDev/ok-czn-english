"""Drive the game's menus through the running mode from a command file, for the account scan.

Burak asked for the account state to be gathered on request, with the menus (combatants, partners, memory fragments,
save data) opened by the tools rather than by him. Hub CZN records what the game sends as those screens load; this
module opens them.

Commands are a JSON list in `komut.json` beside the status file, taken one per frame:

    {"tikla": [x, y]}                          click at screen fractions
    {"tikla_metin": "Combatants", "bolge": [x1, y1, x2, y2], "dene": 10}
                                               click the first OCR box whose text contains this (case-insensitive),
                                               optionally only inside a region, trying for up to `dene` frames
    {"tus": "esc"}                             send a key
    {"bekle": 2}                               wait, in seconds
    {"goruntu": true}                          save a snapshot of the screen and the text read off it
    {"surukle": [x1, y1, x2, y2]}              drag, held still before letting go so nothing flings
    {"tut": true}                              hold the screen: the mode keeps waiting until the file is replaced,
                                               so a menu opened for a look is not closed by the mode's own handlers

While the file exists the mode does nothing else, so its own handlers do not act on the screens being opened. When the
list is done, or a command fails, the file is removed and `komut-sonuc.json` records every command and its outcome.
"""

import json
import time

from ok import Logger

from src.en import status

logger = Logger.get_logger(__name__)

COMMANDS_NAME = "komut.json"
RESULT_NAME = "komut-sonuc.json"
DEFAULT_TRIES = 10
DRAG_SECONDS = 3.0
DRAG_HOLD = 0.5
# Held on the task between frames.
LOG = "_en_remote_log"
TRIES = "_en_remote_tries"


def commands_path():
    return status.PATH.parent / COMMANDS_NAME


def result_path():
    return status.PATH.parent / RESULT_NAME


def read_commands():
    """The commands still to run, or None when there is no command file (or it cannot be read)."""
    path = commands_path()
    if not path.exists():
        return None
    try:
        commands = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        logger.warning(f"command file unreadable, dropped: {error}")
        path.unlink(missing_ok=True)
        return None
    return commands if isinstance(commands, list) else None


def finish(task, outcome):
    """Record what ran and hand the screen back to the mode."""
    log = getattr(task, LOG, None) or []
    result_path().write_text(json.dumps({"sonuc": outcome, "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                         "komutlar": log}, ensure_ascii=False, indent=1), encoding="utf-8")
    commands_path().unlink(missing_ok=True)
    setattr(task, LOG, [])
    setattr(task, TRIES, 0)
    task.log_info(f"remote commands {outcome}, {len(log)} run")


def find_text(task, wanted, region=None):
    from src.en.screen import in_region

    wanted = wanted.casefold().replace(" ", "")
    for box in task.all_texts or []:
        name = (box.name or "").casefold().replace(" ", "")
        if wanted in name and (region is None or in_region(box, tuple(region), task.width, task.height)):
            return box
    return None


def run(task, command):
    """Carry out one command.

    Returns:
        "ok" when done, "again" to try it on the next frame, or a failure message.
    """
    if "tikla" in command:
        x, y = command["tikla"]
        task.click_relative(float(x), float(y))
        return "ok"
    if "tikla_metin" in command:
        box = find_text(task, str(command["tikla_metin"]), command.get("bolge"))
        if box is None:
            tries = getattr(task, TRIES, 0) + 1
            setattr(task, TRIES, tries)
            if tries < int(command.get("dene", DEFAULT_TRIES)):
                return "again"
            return f"text not found: {command['tikla_metin']}"
        task.click_box(box)
        return "ok"
    if "tus" in command:
        task.send_key(str(command["tus"]))
        return "ok"
    if "bekle" in command:
        task.sleep(float(command["bekle"]))
        return "ok"
    if "goruntu" in command:
        from src.en import snapshot

        frame = getattr(task, "frame", None)
        image = snapshot.save(task, frame, 0) if frame is not None else None
        return "ok" if image else "no frame to save"
    if "tut" in command:
        return "hold"
    if "surukle" in command:
        x1, y1, x2, y2 = command["surukle"]
        task.swipe_relative(float(x1), float(y1), float(x2), float(y2), duration=DRAG_SECONDS, settle_time=DRAG_HOLD)
        return "ok"
    return f"unknown command: {command}"


def step(task):
    """Take this frame for the next command while a command file exists.

    Returns:
        True while commands are being run, so nothing else acts on the frame.
    """
    commands = read_commands()
    if commands is None:
        return False
    if not commands:
        finish(task, "done")
        return True
    command = commands[0]
    outcome = run(task, command)
    if outcome == "hold":
        # Report what ran before the hold once, so a watcher knows the screen is ready to look at.
        log = getattr(task, LOG, None) or []
        if log:
            result_path().write_text(json.dumps({"sonuc": "holding", "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                 "komutlar": log}, ensure_ascii=False, indent=1), encoding="utf-8")
            setattr(task, LOG, [])
        return True
    if outcome == "again":
        return True
    log = getattr(task, LOG, None) or []
    log.append({"komut": command, "sonuc": outcome})
    setattr(task, LOG, log)
    setattr(task, TRIES, 0)
    if outcome != "ok":
        finish(task, f"failed at command {len(log)}: {outcome}")
        return True
    task.log_info(f"remote command {len(log)} done: {command}")
    rest = commands[1:]
    if rest:
        commands_path().write_text(json.dumps(rest, ensure_ascii=False), encoding="utf-8")
    else:
        finish(task, "done")
    task.sleep(0.5)
    return True
