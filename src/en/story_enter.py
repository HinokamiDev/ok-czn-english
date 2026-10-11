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
# The box is also found by its frame, for lines OCR reads nothing off ("… …" stalled a walk for three minutes).
# Measured on six live captures: with the box up its top and bottom rules stand ~30 grey levels above their band and
# the inside stays dark; without it the rules are under 10 or the inside is bright.
BOX_RULES = ((0.115, 0.145), (0.265, 0.295))
BOX_SPAN = (0.10, 0.40)
BOX_INSIDE = (0.15, 0.26)
BOX_RULE_CONTRAST = 18
BOX_INSIDE_DARK = 40
BOX_CENTRE = (0.25, 0.20)
# A finished stage is announced across the middle of the map ("01 / Warriors of the Arena / Complete", the last read
# live at (0.499, 0.568)) and waits for a tap. Nothing in upstream's Story list answers it.
COMPLETE = "complete"
COMPLETE_REGION = (0.35, 0.52, 0.65, 0.62)
COMPLETE_PRESSED = "_en_story_complete_pressed"
# At the end of a chapter the map shows the next one's number and name on the right ("02 / Desert Kingdom Ruins",
# read live at (0.905, 0.471) and (0.809, 0.532)) behind an arrow. With no stage left to enter, the Story mode stood
# still there. The arrow is taken only when no stage entrance is on screen.
NEXT_CHAPTER_NUMBER_REGION = (0.84, 0.40, 0.97, 0.52)
NEXT_CHAPTER_NAME_REGION = (0.65, 0.50, 0.97, 0.58)
NEXT_CHAPTER_PRESSED = "_en_story_next_chapter_pressed"
STAGE_ENTRANCES = ("enterstory", "enterbattle")
MAP_REGION = (0.085, 0.124, 0.995, 0.874)
# The chapter's name is only a label - pressing it did nothing live, seven times. The tab of that chapter along the
# top ("Chapter 2" at (0.606, 0.04)) is pressed instead, or the arrow beside the name when no tab shows it.
CHAPTER_TABS_REGION = (0.25, 0.0, 0.75, 0.08)
NEXT_CHAPTER_ARROW = (0.961, 0.503)
# A chapter's next stage can sit past the right edge of the map, its number cut off ("#" at (0.987, 0.503) in Chapter
# 3) and its play button out of view, so nothing was entered. The map is dragged left to bring it in.
EDGE_STAGE_REGION = (0.93, 0.40, 1.0, 0.70)
MAP_DRAG = ((0.80, 0.62), (0.30, 0.62))
MAP_DRAG_PRESSED = "_en_story_map_drag"
# A chaos stage on the story map is captioned "Observe" ("#07 Observe" in Chapter 3, read live at (0.567, 0.504));
# upstream looks for the Chinese 观测, so it was never pressed. It is a Chaos run the Story mode cannot play: after
# pressing it the run is handed to the Chaos mode, and the Story mode is started again when that run stops.
OBSERVE = "observe"
OBSERVE_REGION = (0.092, 0.214, 0.962, 0.792)
OBSERVE_PRESSED = "_en_story_observe_pressed"
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


def handle_next_chapter(task, utils_sortie=None):
    """Move on to the next chapter once the map has no stage left to enter.

    Args:
        task: The running task.
        utils_sortie: Unused; every step takes the same arguments.

    Returns:
        True when the next chapter was opened.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    texts = task.all_texts or []
    number = next((box for box in texts if (box.name or "").strip().isdigit() and len(box.name.strip()) == 2
                   and in_region(box, NEXT_CHAPTER_NUMBER_REGION, width, height)), None)
    name = next((box for box in texts if len((box.name or "").strip()) > 3
                 and in_region(box, NEXT_CHAPTER_NAME_REGION, width, height)), None)
    if number is None or name is None:
        return False
    search = task.box_of_screen(*MAP_REGION)
    if any(task.find_feature(feature_name=feature, box=search) for feature in STAGE_ENTRANCES):
        return False
    last = getattr(task, NEXT_CHAPTER_PRESSED, None)
    if last and time.monotonic() - last < OPTION_COOLDOWN:
        return False
    wanted = f"chapter {int(number.name.strip())}"
    tab = next((box for box in texts if (box.name or "").strip().casefold() == wanted
                and in_region(box, CHAPTER_TABS_REGION, width, height)), None)
    task.log_info(f"no stage left on this map, moving on to chapter {number.name.strip()} '{name.name.strip()}'"
                  f" by its {'tab' if tab else 'arrow'}")
    if tab is not None:
        task.click_box(tab)
    else:
        task.click_relative(*NEXT_CHAPTER_ARROW)
    setattr(task, NEXT_CHAPTER_PRESSED, time.monotonic())
    task.sleep(2)
    return True


def handle_map_drag(task, utils_sortie=None):
    """Drag the chapter map left when the next stage is cut off at its right edge.

    Args:
        task: The running task.
        utils_sortie: Unused; every step takes the same arguments.

    Returns:
        True when the map was dragged.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    texts = task.all_texts or []
    on_map = any((box.name or "").strip().casefold().startswith("chapter")
                 and in_region(box, CHAPTER_TABS_REGION, width, height) for box in texts)
    edge = next((box for box in texts if (box.name or "").strip().startswith("#")
                 and in_region(box, EDGE_STAGE_REGION, width, height)), None)
    if not on_map or edge is None:
        return False
    search = task.box_of_screen(*MAP_REGION)
    if any(task.find_feature(feature_name="enterstory", box=search) or []):
        return False
    last = getattr(task, MAP_DRAG_PRESSED, None)
    if last and time.monotonic() - last < OPTION_COOLDOWN:
        return False
    task.log_info(f"next stage cut off at the map's right edge ('{edge.name.strip()}'), dragging the map left")
    (x1, y1), (x2, y2) = MAP_DRAG
    task.swipe_relative(x1, y1, x2, y2, duration=0.6)
    setattr(task, MAP_DRAG_PRESSED, time.monotonic())
    task.sleep(1)
    return True


def handle_observe_stage(task, utils_sortie=None):
    """Enter a chaos stage from the story map and hand its run to the Chaos mode.

    Args:
        task: The running task.
        utils_sortie: Unused; every step takes the same arguments.

    Returns:
        True when the stage was entered.
    """
    from src.en import autostart
    from src.en.screen import in_region

    stage = next((box for box in task.all_texts or [] if (box.name or "").strip().casefold() == OBSERVE
                  and in_region(box, OBSERVE_REGION, task.width, task.height)), None)
    if stage is None:
        return False
    last = getattr(task, OBSERVE_PRESSED, None)
    if last and time.monotonic() - last < 30:
        return False
    task.log_info("chaos stage on the story map, entering it and handing the run to the Chaos mode")
    task.click_box(stage)
    setattr(task, OBSERVE_PRESSED, time.monotonic())
    task.sleep(4)
    autostart.request_switch("ChaosMode", then_story=True)
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
        # A step that fails costs this frame, not the run: a step reloaded live once called a function its
        # not-yet-reloaded neighbour lacked, and the AttributeError stopped the Story mode.
        try:
            if globals()[step](task, utils_sortie):
                return True
        except Exception as error:
            logger.error(f"Story step {step} failed: {error!r}", exception=error)
    return False


def speech_box_on_screen(frame):
    """Say whether a walk's speech box is drawn, from its frame rather than its text.

    Args:
        frame: The BGR frame, or None.

    Returns:
        True when both rules of the box stand out and its inside is dark.
    """
    import numpy as np

    if frame is None:
        return False
    height, width = frame.shape[:2]
    # Only the box's corner of the frame is greyed, which keeps this cheap enough to run on every Story frame.
    corner = frame[:int(0.30 * height), :int(BOX_SPAN[1] * width)]
    grey = corner.mean(axis=2) if corner.ndim == 3 else corner.astype(float)
    columns = slice(int(BOX_SPAN[0] * width), int(BOX_SPAN[1] * width))
    for top, bottom in BOX_RULES:
        rows = [grey[y, columns].mean() for y in range(int(top * height), int(bottom * height))]
        if not rows or max(rows) - float(np.median(rows)) < BOX_RULE_CONTRAST:
            return False
    inside = grey[int(BOX_INSIDE[0] * height):int(BOX_INSIDE[1] * height), columns]
    return float(inside.mean()) < BOX_INSIDE_DARK


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
    if not lines and speech_box_on_screen(getattr(task, "frame", None)):
        last = getattr(task, WALK_DIALOGUE_PRESSED, None)
        if last and last[0] is None and time.monotonic() - last[1] < WALK_DIALOGUE_COOLDOWN:
            return False
        task.log_info("speech box with no readable line, clicking on")
        task.click_relative(*BOX_CENTRE)
        setattr(task, WALK_DIALOGUE_PRESSED, (None, time.monotonic()))
        task.sleep(0.5)
        return True
    # Up to four: a line wraps to three in the box ("Ah...? I don't know why, but... / it feels like the magical power
    # has / weakened...!" stalled a walk when two was the limit).
    if not lines or len(lines) > 4:
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


def handle_speech_box_anywhere(task, utils_sortie=None):
    """Click on a speech box in the Chaos and Sortie modes, where story stages run their own scenes too.

    Only the box's frame decides here - those modes fill the top-left with their own text - so a box OCR read nothing
    off is caught as well. Live: "I agree." held a story chaos stage for over half a minute.

    Returns:
        True when the box was clicked.
    """
    if not speech_box_on_screen(getattr(task, "frame", None)):
        return False
    last = getattr(task, WALK_DIALOGUE_PRESSED, None)
    if last and time.monotonic() - last[1] < WALK_DIALOGUE_COOLDOWN:
        return False
    task.log_info("speech box on screen, clicking on")
    task.click_relative(*BOX_CENTRE)
    setattr(task, WALK_DIALOGUE_PRESSED, ("box", time.monotonic()))
    task.sleep(0.5)
    return True


TOUCH_TO_START = "touch to start"
TOUCH_REGION = (0.25, 0.70, 0.75, 0.88)


def handle_touch_to_start(task, utils_sortie=None):
    """Tap the title screen the game opens on after a restart ("TOUCH TO START" at about (0.5, 0.8)).

    Returns:
        True when it was tapped.
    """
    from src.en.screen import in_region

    # Spaces dropped: OCR read it live as "TOUCHTOSTART".
    wanted = TOUCH_TO_START.replace(" ", "")
    title = next((box for box in task.all_texts or [] if wanted in (box.name or "").replace(" ", "").casefold()
                  and in_region(box, TOUCH_REGION, task.width, task.height)), None)
    if title is None:
        return False
    task.log_info("title screen, touching to start")
    task.click_box(title)
    task.sleep(3)
    return True


RECONNECT_QUESTION = "connection was lost"
RECONNECT_REGION = (0.15, 0.38, 0.85, 0.53)
CONTINUE_CAPTIONS = ("继续", "continue")
CONTINUE_REGION = (0.50, 0.70, 0.85, 0.84)


def handle_chaos_reconnect(task, utils_sortie=None):
    """Continue a Chaos run the game offers to resume after a restart.

    Read live: "Chaos connection was lost unexpectedly. Would you like to continue?" at (0.501, 0.457), with Escape at
    (0.377, 0.766) and Continue (继续) at (0.642, 0.767). The dialogue handler kept tapping the question instead.

    Returns:
        True when Continue was pressed.
    """
    from src.en.screen import text_in_region

    if text_in_region(task, RECONNECT_QUESTION, RECONNECT_REGION) is None:
        return False
    button = next((found for caption in CONTINUE_CAPTIONS
                   for found in [text_in_region(task, caption, CONTINUE_REGION)] if found is not None), None)
    if button is None:
        return False
    task.log_info("the game offers to resume the interrupted Chaos run, continuing it")
    task.click_box(button)
    task.sleep(3)
    return True


STORY_LABELS = ("故事", "story")
STORY_LABEL_REGION = (0.0, 0.0, 0.20, 0.10)


def handle_back_on_story_map(task, utils_sortie=None):
    """Hand back to the Story mode once a chaos stage it handed over has ended on the story map.

    The Chaos mode counts a run as done on its own result screen. A story chaos stage returned straight to the story
    map instead ("Toward the Abyss #07" ticked off, Chapter 3), so the Chaos mode ran on over a screen it has no use
    for and the return to Story never came.

    Returns:
        True when the hand-back was asked for.
    """
    from src.en import autostart
    from src.en.screen import in_region

    if not (status_folder() / autostart.RETURN_NAME).exists() or getattr(task, "name", "") == "半自动剧情模式":
        return False
    texts = task.all_texts or []
    labelled = any((box.name or "").strip().casefold() in STORY_LABELS
                   and in_region(box, STORY_LABEL_REGION, task.width, task.height) for box in texts)
    chapter = any((box.name or "").strip().casefold().startswith("chapter")
                  and in_region(box, CHAPTER_TABS_REGION, task.width, task.height) for box in texts)
    if not (labelled and chapter):
        return False
    task.log_info("back on the story map after the chaos stage, handing back to the Story mode")
    (status_folder() / autostart.RETURN_NAME).unlink(missing_ok=True)
    autostart.request_switch("StoryMode")
    task.sleep(3)
    return True


def status_folder():
    from src.en import status
    return status.PATH.parent


def handle_fork_steps(task, utils_sortie=None):
    """Run the steps this fork adds to the Chaos and Sortie modes, first that answers wins; reloadable like Story's."""
    for step in GENERAL_STEPS:
        try:
            if globals()[step](task, utils_sortie):
                return True
        except Exception as error:
            logger.error(f"step {step} failed: {error!r}", exception=error)
    return False


GENERAL_STEPS = ("handle_touch_to_start", "handle_chaos_reconnect", "handle_back_on_story_map",
                 "handle_speech_box_anywhere")
GENERAL_MODES = ("utils_chaos", "utils_sortie")


def place_general_steps():
    """Put the general step runner near the top of the Chaos and Sortie lists, once."""
    for module_name, handlers in each_list():
        if module_name not in GENERAL_MODES:
            continue
        if any(getattr(handler, "__name__", None) == handle_fork_steps.__name__ for handler in handlers):
            continue
        handlers.insert(1, proxy(__name__, handle_fork_steps.__name__))
        logger.info(f"{module_name}: fork steps placed at 1")


# Looked up by name at each call, so a reload that edits this list or the steps takes effect at once.
STORY_STEPS = ("handle_touch_to_start", "handle_chaos_reconnect", "handle_stage_complete", "walk_dialogue_step", "handle_observe_stage", "handle_next_chapter",
               "handle_map_drag")


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
    place_general_steps()


def apply():
    """Let the Story mode press a stage's Enter button on the Global client."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
