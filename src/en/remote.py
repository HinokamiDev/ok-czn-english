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
    {"varsa": "Notice", "tikla": [x, y]}       click at a point only if this text shows within `dene` frames
    {"yoksa": "Simulation", "tikla": [x, y]}   click at a point only if this text is not on screen (one frame)
    {"politika": {"Public Order": 65}}         Policy Office: stamp the document that brings the city's indexes
                                               nearest their targets (read off the left panel); "no policy" when
                                               no pair of documents is up
    {"kalp": 0}                                click the agent pin under the N-th pink heart from the left (Ark City
                                               excursion map, where the agents move about between visits)
    {"lobiye_don": true, "dene": 150}          from the title screen or the lobby's opening pop-ups to the lobby
    Any command with "istege_bagli": true is skipped, not failed, when its text never shows.
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


# The lobby, recognised by its menu down the right ("Simulation", "Combatants" read at x 0.87).
LOBBY_WORDS = ("simulation", "combatants")
LOBBY_REGION = (0.75, 0.25, 1.0, 0.70)
# What stands between a fresh login and the lobby, each with where to press it (snapshots 20261012-005808..005850).
TITLE_TEXT = "touchtostart"
SKIP_TEXT = "skip"
SKIP_REGION = (0.85, 0.0, 1.0, 0.12)
TAP_TO_CLOSE = "点击屏幕关闭窗口"
# A run's result screen ("Battle failed", reward grid) closes with Confirm at the bottom right (20261014-010104).
RESULT_CONFIRM = "确认"
RESULT_CONFIRM_REGION = (0.75, 0.85, 1.0, 0.98)
# Then "Save Data collection complete" and "Mental affliction triggered", each with Next there (20261014-0103..0104).
# The Chaos mode stops as soon as its last run is counted, so these were still up when Story took over.
RESULT_NEXT = "下一步"
# After a run, the new save's detail window opens over the result ("Save Data" top left, "Can Apply Mutation" lower
# left) and closes with the X at its top right (20261020-153147, 164559).
SAVE_POPUP_TEXTS = ("canapplymutation", "savedata")
SAVE_POPUP_CLOSE = (0.881, 0.15)
# Login banners over the lobby ("Seasonal Rossweisse ... Go to Rescue", 20261021-081117) close with the X top right.
BANNER_TEXTS = ("gotorescue", "gotoevent", "gotoshop", "rate-up")
BANNER_REGION = (0.0, 0.70, 1.0, 1.0)
BANNER_CLOSE = (0.968, 0.052)
# The Save Data page itself reads the same two texts, and there the X spot is its Edit Data button (20 Oct, 17:00).
SAVE_PAGE_TEXTS = ("editdata", "cancelediting", "dismantle", "obtain")
# A menu screen (Team Formation "主战员配置", Chaos Manifestation...) has its title top left and goes back with the arrow
# at BACK_POINT. The lobby's own corner reads "LV" and the captain's name there, and the arrow would open the ID card.
BACK_TITLE_REGION = (0.07, 0.0, 0.40, 0.09)
BACK_POINT = (0.042, 0.044)
# OCR reads "LV" through the catalog as "等级" (20261020-115836); either is taken.
LOBBY_CORNER = ("lv", "等级")
LOBBY_CORNER_REGION = (0.0, 0.0, 0.10, 0.14)
NOTICE_TABS = ("notice", "update")
NOTICE_REGION = (0.10, 0.05, 0.50, 0.18)
NOTICE_CLOSE = (0.910, 0.119)
LOBBY_TRIES = 150
REVEAL_TAP = (0.45, 0.80)
REVEAL_EVERY = 3

HOVER_SECONDS = 0.5


def press(task, x, y):
    """Click at screen fractions with the pointer brought there first, as upstream's `_move_and_click` does.

    A bare click was swallowed live on Arkhianon Supply's Claim All and the lobby's festival icon (14 and 20 Oct): those
    buttons take a click only once the pointer has entered them. Fixed timing, nothing random.
    """
    try:
        task.move_relative(x, y)
    except Exception as error:
        # Refused while another window is in front; the click below is then lost too, and the snapshot shows it.
        if "SetCursorPos" not in str(error):
            raise
    task.sleep(HOVER_SECONDS)
    task.click_relative(x, y)


def in_lobby(task):
    return all(find_text(task, word, LOBBY_REGION) is not None for word in LOBBY_WORDS)


def toward_lobby(task):
    """One step from the title screen or an opening pop-up toward the lobby.

    Returns:
        True when the lobby is on screen.
    """
    if in_lobby(task):
        return True
    for wanted, region in ((TITLE_TEXT, None), (SKIP_TEXT, SKIP_REGION), (TAP_TO_CLOSE, None),
                           (RESULT_CONFIRM, RESULT_CONFIRM_REGION), (RESULT_NEXT, RESULT_CONFIRM_REGION)):
        box = find_text(task, wanted, region)
        if box is not None:
            task.click_box(box)
            task.sleep(2)
            return False
    if (all(find_text(task, word) is not None for word in SAVE_POPUP_TEXTS)
            and all(find_text(task, word) is None for word in SAVE_PAGE_TEXTS)):
        press(task, *SAVE_POPUP_CLOSE)
        task.sleep(2)
        return False
    if any(find_text(task, word, BANNER_REGION) is not None for word in BANNER_TEXTS) and not in_lobby(task):
        press(task, *BANNER_CLOSE)
        task.sleep(2)
        return False
    if any(find_text(task, tab, NOTICE_REGION) is not None for tab in NOTICE_TABS):
        press(task, *NOTICE_CLOSE)
        task.sleep(2)
        return False
    from src.en.screen import in_region

    tries = getattr(task, TRIES, 0)
    titled = any(in_region(box, BACK_TITLE_REGION, task.width, task.height) and len((box.name or "").strip()) >= 2
                 for box in task.all_texts or [])
    if titled and all(find_text(task, word, LOBBY_CORNER_REGION) is None for word in LOBBY_CORNER):
        # A menu: only its back arrow, never the lobby's wake-up tap, which on Simulation landed on the Basin of
        # Hyperspace card and walked off further (20 Oct, 14:03).
        if tries % REVEAL_EVERY == 1:
            press(task, *BACK_POINT)
            task.sleep(2)
        return False
    # The lobby hides its menus after a while untouched; a tap on an empty spot brings them back (Burak, 12 Oct).
    # Every third frame, so a screen still loading is not tapped on every frame.
    if getattr(task, TRIES, 0) % REVEAL_EVERY == REVEAL_EVERY - 1:
        press(task, *REVEAL_TAP)
        task.sleep(1)
    return False



# Ark City's excursion map marks each agent with a pink heart above the portrait pin (20261020-120834: hearts about
# 22x20 of 1280x720, BGR about (156, 111, 255)); the portrait is clicked, down and right of the heart.
HEART_HSV = ((160, 90, 180), (179, 220, 255))
HEART_AREA = (2.5e-4, 4.8e-4)
HEART_TO_PIN = (0.017, 0.045)


def heart_pins(frame):
    """The agent pins' click points, left to right, as screen fractions."""
    import cv2

    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *HEART_HSV)
    count, _, stats, centres = cv2.connectedComponentsWithStats(mask)
    pins = []
    for index in range(1, count):
        area = stats[index][cv2.CC_STAT_AREA] / (width * height)
        box_w, box_h = stats[index][cv2.CC_STAT_WIDTH], stats[index][cv2.CC_STAT_HEIGHT]
        if HEART_AREA[0] <= area <= HEART_AREA[1] and 0.8 <= box_w / max(box_h, 1) <= 1.4:
            x, y = centres[index]
            pins.append((x / width + HEART_TO_PIN[0], y / height + HEART_TO_PIN[1]))
    return sorted(pins)


# Ark City Policy Office (20261020-125940, 130045): two documents side by side, each listing "Increase/Reduce <index> by
# N", and a stamp to drag onto the one approved. The left panel reads each index as "60/100".
POLICY_INDEXES = ("Public Order", "Happiness", "Administrative", "Economic Activity")
POLICY_DOCUMENTS = ((0.50, 0.15, 0.735, 0.70), (0.75, 0.13, 0.985, 0.70))
POLICY_DROP = ((0.61, 0.45), (0.86, 0.45))
POLICY_STAMP = (0.735, 0.80)
POLICY_PANEL = (0.0, 0.58, 0.26, 0.95)


def policy_effects(task, region):
    """The index changes one document lists, as {index: signed amount}."""
    import re
    from src.en.screen import in_region

    boxes = sorted((box for box in task.all_texts or [] if in_region(box, region, task.width, task.height)),
                   key=lambda box: (box.y, box.x))
    text = " ".join((box.name or "") for box in boxes)
    effects = {}
    for verb, name, amount in re.findall(r"\b(Increase|Reduce)\b\s*([A-Za-z ]+?)\s*(?:Index\s*)?by\s*(\d+)", text):
        index = next((known for known in POLICY_INDEXES if known.replace(" ", "").lower() in name.replace(" ", "").lower()),
                     None)
        if index:
            effects[index] = effects.get(index, 0) + (int(amount) if verb == "Increase" else -int(amount))
    return effects


def policy_levels(task):
    """The indexes' current values off the left panel, top to bottom, as {index: value}."""
    import re
    from src.en.screen import in_region

    panel = [box for box in task.all_texts or [] if in_region(box, POLICY_PANEL, task.width, task.height)]
    levels = {}
    for box in panel:
        index = next((known for known in POLICY_INDEXES
                      if known.replace(" ", "").lower() in (box.name or "").replace(" ", "").lower()), None)
        if index is None:
            continue
        value = min((other for other in panel if re.fullmatch(r"\d+/100", (other.name or "").strip())),
                    key=lambda other: abs(other.y - box.y), default=None)
        if value is not None and abs(value.y - box.y) < 0.04 * task.height:
            levels[index] = int(value.name.split("/")[0])
    return levels


def policy_score(effects, levels, targets):
    """Progress toward the targets (a drop below one counts against), with a small credit for any other rise."""
    score = 0.0
    for index, change in effects.items():
        now = levels.get(index, 0)
        after = max(0, min(100, now + change))
        target = targets.get(index)
        if target is not None:
            score += 10 * (min(after, target) - min(now, target))
        score += 0.1 * (after - now)
    return score

def tried(task, command, default=DEFAULT_TRIES):
    """Count one more frame spent on this command; say whether it has had its tries."""
    tries = getattr(task, TRIES, 0) + 1
    setattr(task, TRIES, tries)
    return tries >= int(command.get("dene", default))


def run(task, command):
    """Carry out one command.

    Returns:
        "ok" when done, "again" to try it on the next frame, "skipped", or a failure message.
    """
    if "lobiye_don" in command:
        if toward_lobby(task):
            return "ok"
        return "lobby not reached" if tried(task, command, LOBBY_TRIES) else "again"
    if "yoksa" in command:
        if find_text(task, str(command["yoksa"]), command.get("bolge")) is not None:
            return "skipped"
        x, y = command["tikla"]
        press(task, float(x), float(y))
        return "ok"
    if "varsa" in command:
        if find_text(task, str(command["varsa"]), command.get("bolge")) is None:
            return "skipped" if tried(task, command) else "again"
        x, y = command["tikla"]
        press(task, float(x), float(y))
        return "ok"
    if "kalp" in command:
        frame = getattr(task, "frame", None)
        pins = heart_pins(frame) if frame is not None else []
        wanted = int(command["kalp"])
        if wanted >= len(pins):
            return "no agent pin" if tried(task, command) else "again"
        press(task, *pins[wanted])
        return "ok"
    if "tikla" in command:
        x, y = command["tikla"]
        press(task, float(x), float(y))
        return "ok"
    if "tikla_metin" in command:
        box = find_text(task, str(command["tikla_metin"]), command.get("bolge"))
        if box is None:
            if not tried(task, command):
                return "again"
            return "skipped" if command.get("istege_bagli") else f"text not found: {command['tikla_metin']}"
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
    if "politika" in command:
        targets = {key: int(value) for key, value in (command["politika"] or {}).items()}
        effects = [policy_effects(task, region) for region in POLICY_DOCUMENTS]
        if not all(effects):
            return "no policy" if tried(task, command) else "again"
        levels = policy_levels(task)
        scores = [policy_score(effect, levels, targets) for effect in effects]
        chosen = 0 if scores[0] >= scores[1] else 1
        task.log_info(f"policy: levels {levels}, left {effects[0]} = {scores[0]:.1f}, right {effects[1]} = "
                      f"{scores[1]:.1f}, stamping the {'left' if chosen == 0 else 'right'}")
        task.swipe_relative(*POLICY_STAMP, *POLICY_DROP[chosen], duration=DRAG_SECONDS, settle_time=DRAG_HOLD)
        return "ok"
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
    if outcome not in ("ok", "skipped"):
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
