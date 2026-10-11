"""Press a Story stage's Enter button on the Global client.

Upstream's `handle_enter_stage` looks at the stage panel's button, at (0.820, 0.931), for the Chinese client's
caption "入场". The Global client captions it "Enter", which the catalog turns into "进入", so the button was never
pressed: the Story mode clicked the stage node on the map again every four seconds and the panel just stayed open.
The fork's own Enter handler only presses the round action button further right, so it never covered this one either.
"""

import re
import time

from ok import Logger

from src.en.handlers import insert_before, loaded, register, wrap
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
OPTION_ANCHOR = "handle_view_event"
OPTION_PRESSED = "_en_story_option_pressed"
OPTION_COOLDOWN = 5
# Options without an encounter line look the same and stalled the walk too, so a walk screen is recognised by the
# party's health along the top-left ("356/356" at (0.211, 0.038)) and any short text in the band is taken.
HEALTH = re.compile(r"^\d+\s*/\s*\d+$")
HEALTH_REGION = (0.05, 0.0, 0.45, 0.09)
MAX_OPTION_LINES = 4

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
        if time.monotonic() - (getattr(task, AUTO_CHAT_PRESSED, None) or float("-inf")) < AUTO_CHAT_COOLDOWN:
            return False
        pressed = handle_auto_chat(task)
        if pressed:
            setattr(task, AUTO_CHAT_PRESSED, time.monotonic())
        return pressed

    return wrapped


def pressing_enter(handle_enter_stage, utils):
    """Wrap `handle_enter_stage` so the Global client's caption counts as the button.

    Args:
        handle_enter_stage: The handler to wrap, upstream's or another patch's.
        utils: The module holding `find_box_at_point` and `_clean_match`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        box = utils.find_box_at_point(task, *BUTTON_POINT)
        if box and STAGE_CAPTION not in box.name and (utils._clean_match(box.name, ENTER) or "enter" in box.name.casefold()):
            task.log_info("stage panel's Enter button, pressing it")
            task.click_box(box)
            task.sleep(1)
            return True
        return handle_enter_stage(task)

    return wrapped


def install():
    """Wrap the Story stage handler once both modules are loaded."""
    utils, utils_story = loaded("utils"), loaded("utils_story")
    if utils is None or utils_story is None:
        return
    wrap(utils_story, "handle_enter_stage", lambda original: pressing_enter(original, utils), TAG)
    insert_before(CONFIRM_ANCHOR, handle_skip_dialogue_confirm)
    wrap(utils_story, "handle_auto_chat", pressing_auto_chat_once, AUTO_CHAT_TAG)
    insert_before(OPTION_ANCHOR, handle_story_event_option)


def apply():
    """Let the Story mode press a stage's Enter button on the Global client."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
