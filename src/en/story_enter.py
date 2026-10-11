"""Press a Story stage's Enter button on the Global client.

Upstream's `handle_enter_stage` looks at the stage panel's button, at (0.820, 0.931), for the Chinese client's
caption "入场". The Global client captions it "Enter", which the catalog turns into "进入", so the button was never
pressed: the Story mode clicked the stage node on the map again every four seconds and the panel just stayed open.
The fork's own Enter handler only presses the round action button further right, so it never covered this one either.
"""

import re
import time

from ok import Logger

from src.en.handlers import each_list, insert_before, loaded, register, wrap
from src.en.live import proxy
from src.en.screen import text_in_region

logger = Logger.get_logger(__name__)

TAG = "Global Enter caption"
# Where upstream reads the button, and the captions that mean it.
BUTTON_POINT = (0.820, 0.931)
STAGE_CAPTION = "入场"
ENTER = "进入"

# The dialogue skip asks to be confirmed in a box across the middle of the screen. Upstream's Story `handle_confirm`
# only looks along the bottom edge, so the box stayed up. Read live: title at (0.501, 0.314), Confirm at (0.666, 0.683).
SKIP_QUESTION = "skip the current dialogue"
QUESTION_REGION = (0.15, 0.22, 0.85, 0.40)
CONFIRM = "确认"
CONFIRM_REGION = (0.50, 0.60, 0.85, 0.76)
CONFIRM_ANCHOR = "handle_confirm"
# Upstream's auto-dialogue check calls the toggle off below a 0.96 template match, but on the Global client the
# switched-on toggle matches at 0.85-0.95 too, so it was pressed four times in five seconds - on, off, on, off -
# and the scene was left waiting with Auto off. One press, then time for the toggle to show its new state.
AUTO_CHAT_COOLDOWN = 30
AUTO_CHAT_PRESSED = "_en_auto_chat_pressed"
AUTO_CHAT_TAG = "one auto-dialogue press"
# A story walk offers its next step as a box of text above the bottom edge, such as "Enter the ventilation shaft"
# over "Event Encounter: Rescue Alcea" - read live at (0.475, 0.798) and (0.502, 0.836). Upstream's Story mode only
# looks for a "check" icon there, so the walk stood still. The box is pressed on its first line.
OPTION_BAND = (0.25, 0.68, 0.75, 0.94)
ENCOUNTER = "event encounter"
# Run after upstream's magnifier handler, never before: a walk's magnifiers are all looked at before its option
# moves the walk on, or what they hold is left behind.
OPTION_AFTER = "handle_view_event"
OPTION_PRESSED = "_en_story_option_pressed"
OPTION_COOLDOWN = 5
# Options without an encounter line look the same and stalled the walk too, so a walk screen is recognised by the
# party's health along the top-left ("356/356" at (0.211, 0.038)) and any short text in the band is taken.
HEALTH = re.compile(r"^\d+\s*/\s*\d+$")
HEALTH_REGION = (0.05, 0.0, 0.45, 0.09)
MAX_OPTION_LINES = 4
# A story walk's magnifier is drawn at about 90% of upstream's `check` template, so the template scored 0.48 on a
# live one and was never clicked; scaled to 0.9 it scored 0.92. Upstream's own match is tried first.
MAGNIFIER_SOURCE = ("ok_tasks/assets/images/1.png", (1051, 477, 59, 63))
MAGNIFIER_SCALES = (0.85, 0.9, 0.95)
MAGNIFIER_THRESHOLD = 0.8
MAGNIFIER_REGION = (0.084, 0.125, 0.995, 0.875)
MAGNIFIER_PRESSED = "_en_story_magnifier_pressed"
MAGNIFIER_TAG = "scaled magnifier"
# A story walk speaks in a box under the health bar, a portrait on its left and a ▽ in its corner, and waits for a
# click to go on - read live: "Isn't this just a pillar?" at (0.182, 0.203). Upstream's Story mode knows no such box.
WALK_DIALOGUE_REGION = (0.08, 0.11, 0.45, 0.32)
WALK_DIALOGUE_PRESSED = "_en_story_walk_dialogue_pressed"
WALK_DIALOGUE_COOLDOWN = 2
# A finished stage is announced across the middle of the map ("01 / Warriors of the Arena / Complete", the last read
# live at (0.499, 0.568)) and waits for a tap. Nothing in upstream's Story list answers it.
COMPLETE = "complete"
COMPLETE_REGION = (0.35, 0.52, 0.65, 0.62)
COMPLETE_PRESSED = "_en_story_complete_pressed"
_magnifier = None

_patched = False


def handle_skip_dialogue_confirm(task):
    """Confirm the box that asks whether to skip the current dialogue.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when the box was there and its Confirm pressed.
    """
    if text_in_region(task, SKIP_QUESTION, QUESTION_REGION) is None:
        return False
    confirm = text_in_region(task, CONFIRM, CONFIRM_REGION) or text_in_region(task, "confirm", CONFIRM_REGION)
    if confirm is None:
        return False
    task.log_info("confirming the dialogue skip")
    task.click_box(confirm)
    task.sleep(1)
    return True


def on_story_walk(task, utils_sortie):
    """Say whether the screen is a story walk: the party's health along the top-left, and no fight's hand counter.

    The fight screen shows the party's health too, and its hand names sit in the same band as a walk's options,
    so a hand counter on screen rules it out.
    """
    from src.en.screen import in_region

    health = any(HEALTH.match((box.name or "").strip()) and in_region(box, HEALTH_REGION, task.width, task.height)
                 for box in task.all_texts or [])
    if not health:
        return False
    return utils_sortie is None or utils_sortie._read_hand_count(task) is None


def handle_story_event_option(task, utils_sortie=None):
    """Press the step a story walk offers.

    Args:
        task: The running task, whose `all_texts` is the current screen.
        utils_sortie: The Sortie module, for its hand counter, looked up when not given.

    Returns:
        True when an option was pressed.
    """
    from src.en.screen import in_region

    utils_sortie = utils_sortie or loaded("utils_sortie")
    band = [box for box in task.all_texts or [] if in_region(box, OPTION_BAND, task.width, task.height)]
    if not band or len(band) > MAX_OPTION_LINES:
        return False
    encounter = next((box for box in band if ENCOUNTER in (box.name or "").casefold()), None)
    if encounter is None and not on_story_walk(task, utils_sortie):
        return False
    # The option's first line is its title; an encounter line sits under it.
    title = min(band, key=lambda box: box.y)
    last = getattr(task, OPTION_PRESSED, None)
    if last and last[0] == title.name and time.monotonic() - last[1] < OPTION_COOLDOWN:
        return False
    task.log_info(f"story walk offers {[box.name for box in band]}, pressing '{title.name}'")
    task.click_box(title)
    setattr(task, OPTION_PRESSED, (title.name, time.monotonic()))
    task.sleep(1)
    return True


def pressing_auto_chat_once(handle_auto_chat):
    """Wrap upstream's auto-dialogue check so it presses the toggle at most once per cooldown.

    Args:
        handle_auto_chat: The handler to wrap.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        # The step is looked up in this module at each call, so a live reload of the module replaces it.
        return auto_chat_step(handle_auto_chat, task)

    return wrapped


def auto_chat_step(handle_auto_chat, task):
    if time.monotonic() - (getattr(task, AUTO_CHAT_PRESSED, None) or float("-inf")) < AUTO_CHAT_COOLDOWN:
        return False
    pressed = handle_auto_chat(task)
    if pressed:
        setattr(task, AUTO_CHAT_PRESSED, time.monotonic())
    return pressed


def pressing_enter(handle_enter_stage, utils):
    """Wrap `handle_enter_stage` so the Global client's caption counts as the button.

    Args:
        handle_enter_stage: The handler to wrap, upstream's or another patch's.
        utils: The module holding `find_box_at_point` and `_clean_match`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        return enter_stage_step(handle_enter_stage, utils, task)

    return wrapped


def enter_stage_step(handle_enter_stage, utils, task):
    box = utils.find_box_at_point(task, *BUTTON_POINT)
    if box and STAGE_CAPTION not in box.name and (utils._clean_match(box.name, ENTER) or "enter" in box.name.casefold()):
        task.log_info("stage panel's Enter button, pressing it")
        task.click_box(box)
        task.sleep(1)
        return True
    return handle_enter_stage(task)


def magnifier_template():
    """Cut upstream's `check` template out of its source image, once."""
    global _magnifier
    if _magnifier is None:
        import cv2
        from pathlib import Path

        image = cv2.imread(str(Path(__file__).resolve().parents[2] / MAGNIFIER_SOURCE[0]))
        x, y, w, h = MAGNIFIER_SOURCE[1]
        _magnifier = image[y:y + h, x:x + w] if image is not None else False
    return _magnifier if _magnifier is not False else None


def find_magnifier(frame, region=MAGNIFIER_REGION):
    """Find a story walk's magnifier at the sizes the client draws it.

    Args:
        frame: The BGR frame.
        region: Where to look, in screen fractions.

    Returns:
        The magnifier's centre as screen fractions, or None.
    """
    import cv2

    template = magnifier_template()
    if template is None or frame is None:
        return None
    height, width = frame.shape[:2]
    left, top = int(region[0] * width), int(region[1] * height)
    area = frame[top:int(region[3] * height), left:int(region[2] * width)]
    resolution = width / 1920
    best = None
    for scale in MAGNIFIER_SCALES:
        sized = cv2.resize(template, None, fx=scale * resolution, fy=scale * resolution, interpolation=cv2.INTER_AREA)
        if sized.shape[0] > area.shape[0] or sized.shape[1] > area.shape[1]:
            continue
        _, score, _, at = cv2.minMaxLoc(cv2.matchTemplate(area, sized, cv2.TM_CCOEFF_NORMED))
        if best is None or score > best[0]:
            best = (score, at, sized.shape)
    if best is None or best[0] < MAGNIFIER_THRESHOLD:
        return None
    score, (x, y), (h, w) = best[0], best[1], best[2][:2]
    return (left + x + w / 2) / width, (top + y + h / 2) / height


def looking_closer(handle_view_event):
    """Wrap upstream's magnifier handler with a match at the client's own sizes.

    Args:
        handle_view_event: The handler to wrap.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        return magnifier_step(handle_view_event, task)

    return wrapped


def magnifier_step(handle_view_event, task):
    if handle_view_event(task):
        return True
    found = find_magnifier(getattr(task, "frame", None))
    if found is None:
        return False
    last = getattr(task, MAGNIFIER_PRESSED, None)
    if (last and abs(last[0][0] - found[0]) < 0.02 and abs(last[0][1] - found[1]) < 0.02
            and time.monotonic() - last[1] < OPTION_COOLDOWN):
        return False
    task.log_info(f"story walk magnifier at ({found[0]:.3f}, {found[1]:.3f}), looking at it")
    task.click_relative(*found)
    setattr(task, MAGNIFIER_PRESSED, (found, time.monotonic()))
    task.sleep(0.5)
    return True


def handle_stage_complete(task, utils_sortie=None):
    """Tap away the banner announcing a finished stage.

    Args:
        task: The running task, whose `all_texts` is the current screen.
        utils_sortie: Unused; every step takes the same arguments.

    Returns:
        True when the banner was tapped.
    """
    from src.en.screen import text_in_region

    banner = text_in_region(task, COMPLETE, COMPLETE_REGION)
    if banner is None or (banner.name or "").strip().casefold() != COMPLETE:
        return False
    last = getattr(task, COMPLETE_PRESSED, None)
    if last and time.monotonic() - last < OPTION_COOLDOWN:
        return False
    task.log_info("stage complete banner, tapping it away")
    task.click_box(banner)
    setattr(task, COMPLETE_PRESSED, time.monotonic())
    task.sleep(1)
    return True


def handle_story_walk_dialogue(task, utils_sortie=None):
    """Run the Story steps this fork adds, first that answers wins.

    This is the entry the Story list holds (as a proxy), so a step added to `STORY_STEPS` takes effect on a live
    reload, without a new list entry and so without a restart. Kept under its first name for that reason.

    Args:
        task: The running task.
        utils_sortie: The Sortie module, for its hand counter, looked up when not given.

    Returns:
        True when a step handled the frame.
    """
    for step in STORY_STEPS:
        if globals()[step](task, utils_sortie):
            return True
    return False


def walk_dialogue_step(task, utils_sortie=None):
    """Click a story walk's speech box on, line by line.

    Args:
        task: The running task, whose `all_texts` is the current screen.
        utils_sortie: The Sortie module, for its hand counter, looked up when not given.

    Returns:
        True when the box was clicked.
    """
    from src.en.screen import in_region

    lines = [box for box in task.all_texts or []
             if in_region(box, WALK_DIALOGUE_REGION, task.width, task.height) and len((box.name or "").strip()) > 3]
    if not lines or len(lines) > 2:
        return False
    # Not tied to the health bar or to being out of a fight: a walk's cut-in speaks in this box without the bar
    # ("We need to target its arms first."), and a scripted fight speaks in it mid-turn ("There's an opening near
    # the head!") and takes no card or end-of-turn key until it is clicked on. Nothing else in a fight writes there.
    line = lines[0]
    last = getattr(task, WALK_DIALOGUE_PRESSED, None)
    if last and last[0] == line.name and time.monotonic() - last[1] < WALK_DIALOGUE_COOLDOWN:
        return False
    task.log_info(f"story walk line '{line.name}', clicking on")
    task.click_box(line)
    setattr(task, WALK_DIALOGUE_PRESSED, (line.name, time.monotonic()))
    task.sleep(0.5)
    return True


# Looked up by name at each call, so a reload that edits this list or the steps takes effect at once.
STORY_STEPS = ("handle_stage_complete", "walk_dialogue_step")


def place_after_magnifiers():
    """Put the walk-option handler straight after the magnifier handler, in the Story list only."""
    for module_name, handlers in each_list():
        if module_name != "utils_story":
            continue
        names = [getattr(handler, "__name__", None) for handler in handlers]
        if handle_story_event_option.__name__ in names:
            handlers.pop(names.index(handle_story_event_option.__name__))
            names = [getattr(handler, "__name__", None) for handler in handlers]
        if handle_story_walk_dialogue.__name__ in names:
            handlers.pop(names.index(handle_story_walk_dialogue.__name__))
            names = [getattr(handler, "__name__", None) for handler in handlers]
        index = names.index(OPTION_AFTER) + 1 if OPTION_AFTER in names else len(handlers)
        # Magnifiers, then whatever the walk says, then the option that moves it on.
        # Proxies, so a live reload of this module replaces what the list runs.
        handlers.insert(index, proxy(__name__, handle_story_event_option.__name__))
        handlers.insert(index, proxy(__name__, handle_story_walk_dialogue.__name__))
        logger.info(f"utils_story: walk dialogue and option handlers placed at {index}, after {OPTION_AFTER}")


def install():
    """Wrap the Story stage handler once both modules are loaded."""
    utils, utils_story = loaded("utils"), loaded("utils_story")
    if utils is None or utils_story is None:
        return
    wrap(utils_story, "handle_enter_stage", lambda original: pressing_enter(original, utils), TAG)
    insert_before(CONFIRM_ANCHOR, proxy(__name__, handle_skip_dialogue_confirm.__name__))
    wrap(utils_story, "handle_auto_chat", pressing_auto_chat_once, AUTO_CHAT_TAG)
    wrap(utils_story, "handle_view_event", looking_closer, MAGNIFIER_TAG)
    place_after_magnifiers()


def apply():
    """Let the Story mode press a stage's Enter button on the Global client."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
