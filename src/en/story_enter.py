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
# Shortened: OCR read the last word as "dlialogue" once.
SKIP_QUESTION = "skip the current"
# Act 4 asks it as "Do you want to skip this story?", lower down: question at (0.50, 0.41), Confirm at (0.66, 0.63)
# (snapshot 20261011-221553), and the box stayed up while the skip button was pressed again behind it.
SKIP_QUESTIONS = (SKIP_QUESTION, "skip this story")
# The box grows when it lists the scene's main characters: question at (0.5, 0.212), Confirm at (0.662, 0.786).
QUESTION_REGION = (0.15, 0.15, 0.85, 0.50)
CONFIRM = "确认"
CONFIRM_REGION = (0.50, 0.60, 0.85, 0.86)
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
# The type line printed under a card's name, in English and as the catalog rewrites it. A band carrying one is a hand.
CARD_TYPE_WORDS = ("attac", "upgrad", "skill", "攻击", "强化", "技能")
# A story walk's magnifier is drawn at about 90% of upstream's `check` template, so the template scored 0.48 on a
# live one and was never clicked; scaled to 0.9 it scored 0.92. Upstream's own match is tried first.
MAGNIFIER_SOURCE = ("ok_tasks/assets/images/1.png", (1051, 477, 59, 63))
MAGNIFIER_SCALES = (0.85, 0.9, 0.95)
# Act 4 Chapter 3 put two magnifiers low on the stage, at (0.09, 0.83) and (0.755, 0.885): outside the old region and,
# in the 1280-wide capture, scoring 0.85 and 0.77 (snapshot 20261011-232243). Across the other captures nothing that is
# not a magnifier scored above 0.56.
MAGNIFIER_THRESHOLD = 0.72
MAGNIFIER_REGION = (0.0, 0.125, 1.0, 0.95)
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
BOX_EDGE_STEP = 100
BOX_BAND_DARK = 60
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
# ok-script's window swipe takes its duration in milliseconds, makes one step per 100 of them and sleeps 10 ms a step:
# "0.6 s" was six steps in 60 ms, a fling that carried the map past the next stage to the locked end of Chapter 3
# (snapshot 20261011-234710: #13 and #13-1 locked) and, dragged back, to its start. Thirty steps, then a still
# half-second before letting go, moves it by the drag and no further.
MAP_DRAG_SECONDS = 3.0
MAP_DRAG_HOLD = 0.5
MAP_DRAG_BACK = ((0.30, 0.62), (0.80, 0.62))
MAP_DRAG_PRESSED = "_en_story_map_drag"
# Chapter 3 ended with no next-chapter label on the map at all ("#12 Epilogue II" ticked, nothing to its right), and the
# tab bar's ▷ did nothing. Burak: back out one screen and enter the next chapter from there - so the back button at the
# top left (◁ at (0.042, 0.048)) is pressed, at most every 30s.
CHAPTER_FORWARD = (0.042, 0.048)
CHAPTER_FORWARD_PRESSED = "_en_story_chapter_forward"
CHAPTER_FORWARD_COOLDOWN = 30
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
    if all(text_in_region(task, question, QUESTION_REGION) is None for question in SKIP_QUESTIONS):
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
    # Never while the fight player has a fight: the hand's card names sit in this band, and with the hand counter
    # misread they were pressed as walk options, every six seconds ("Dual Creation", "Upgrade", "Attack").
    fight = getattr(task, "_en_story_fight", None)
    if fight and fight.get("playing"):
        return False
    band = [box for box in task.all_texts or [] if in_region(box, OPTION_BAND, task.width, task.height)]
    if not band or len(band) > MAX_OPTION_LINES:
        return False
    if any(word in (box.name or "").casefold() for box in band for word in CARD_TYPE_WORDS):
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


# A walk can offer several cards side by side ("Follow the phantom on the left / in the middle / on the right", each
# with an "Event [Phantom's Guide] triggered" line under it). The first press only raises a card, with a check mark
# under it that takes it; the single-option press pressed the middle one and the walk waited (snapshot 20261011-224541).
CHOICE_BAND = (0.0, 0.68, 1.0, 0.90)
CHOICE_COLUMN = 0.12
CHOICE_RAISED = 0.025
CHOICE_TAKE_Y = 0.935
# A character's short line above the scene points the way ("It's..this way..." over the left phantom).
HINT_REGION = (0.0, 0.30, 1.0, 0.50)
HINT_LONGEST = 40
CHOICE_PRESSED = "_en_story_choice_pressed"
CHOICE_COOLDOWN = 3


def walk_choice_columns(task):
    """Group the choice band's lines into cards, each a list of boxes from its title down."""
    from src.en.screen import in_region

    band = sorted((box for box in task.all_texts or [] if in_region(box, CHOICE_BAND, task.width, task.height)),
                  key=lambda box: box.y)
    columns = []
    for box in band:
        middle = (box.x + box.width / 2) / task.width
        column = next((column for column in columns if abs(column[0] - middle) < CHOICE_COLUMN), None)
        if column is None:
            columns.append([middle, [box]])
        else:
            column[1].append(box)
    return sorted(columns, key=lambda column: column[0])


# A card mid-fight opens the draw pile to bring cards to hand: "Select up to 1 card(s) to bring to hand." (read in the
# catalog's words), a "0/1" counter, the cards with their type under the name and Select bottom right. It hides the
# hand counter, so the fight player took the fight for over and nothing answered it (snapshot 20261011-231113).
PILE_TITLE = "draw pile"
PILE_TITLE_REGION = (0.0, 0.08, 0.30, 0.20)
PILE_COUNTER_REGION = (0.40, 0.12, 0.60, 0.22)
PILE_COUNTER = re.compile(r"^(\d+)\s*/\s*(\d+)$")
PILE_CARDS_REGION = (0.0, 0.22, 1.0, 0.80)
PILE_SELECT = "选择"
PILE_SELECT_REGION = (0.75, 0.85, 1.0, 1.0)
PILE_ATTACK = "攻击"
PILE_PRESSED = "_en_pile_pressed"
PILE_COOLDOWN = 2


def handle_pile_pick(task, utils_sortie=None):
    """Bring cards from the draw pile to hand, attacks first, then press Select.

    Returns:
        True when a card or Select was pressed.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    texts = task.all_texts or []
    if not any(PILE_TITLE in (box.name or "").casefold() and in_region(box, PILE_TITLE_REGION, width, height)
               for box in texts):
        return False
    select = next((box for box in texts if (box.name or "").strip() == PILE_SELECT
                   and in_region(box, PILE_SELECT_REGION, width, height)), None)
    counter = next((PILE_COUNTER.match((box.name or "").strip()) for box in texts
                    if PILE_COUNTER.match((box.name or "").strip())
                    and in_region(box, PILE_COUNTER_REGION, width, height)), None)
    if select is None:
        return False
    last = getattr(task, PILE_PRESSED, None)
    if last and time.monotonic() - last < PILE_COOLDOWN:
        return False
    # Once a card was picked the counter read "1/1" on screen but OCR missed it (snapshot 20261011-231247), so without
    # a counter the pick made so far stands in for it.
    picked = bool(getattr(task, PILE_PRESSED + "_card", None))
    chosen, wanted = (int(counter.group(1)), int(counter.group(2))) if counter else (int(picked), 1)
    cards = sorted((box for box in texts if in_region(box, PILE_CARDS_REGION, width, height)),
                   key=lambda box: (round(box.y / height, 1), box.x))
    attack = next((box for box in cards if PILE_ATTACK in (box.name or "")), None)
    if chosen < wanted and cards and not getattr(task, PILE_PRESSED + "_card", None):
        card = attack or cards[0]
        task.log_info(f"draw pile asks for {wanted} card(s) to bring to hand, picking the one at "
                      f"({(card.x + card.width / 2) / width:.2f}, {(card.y + card.height / 2) / height:.2f})"
                      f"{' (an attack)' if attack else ''}")
        task.click_box(card)
        setattr(task, PILE_PRESSED + "_card", True)
    else:
        task.log_info(f"draw pile pick at {chosen}/{wanted}, pressing Select")
        task.click_box(select)
        setattr(task, PILE_PRESSED + "_card", False)
    setattr(task, PILE_PRESSED, time.monotonic())
    task.sleep(1)
    return True


def handle_fight_first(task, utils_sortie=None):
    """Give a fight screen to the Story fight player before upstream's stage-entrance match sees it.

    That match read a spot on the battlefield as a stage entrance at 0.85 and clicked it every four seconds, and the
    fight player, further down the list, never got the frame (snapshot 20261011-232659, Act 4 Chapter 3).

    Returns:
        What the fight player returned, or False off a fight screen.
    """
    from src.en import story_fights

    utils_sortie = utils_sortie or loaded("utils_sortie")
    if utils_sortie is None or utils_sortie._read_hand_count(task) is None:
        return False
    return story_fights.handle_story_fight_without_auto(task, utils_sortie)


def handle_walk_choice(task, utils_sortie=None):
    """Take one of several cards a story walk offers: the one a character's line points at, else the first.

    Returns:
        True when a card was raised or taken.
    """
    from src.en.screen import in_region

    utils_sortie = utils_sortie or loaded("utils_sortie")
    fight = getattr(task, "_en_story_fight", None)
    if fight and fight.get("playing"):
        return False
    columns = walk_choice_columns(task)
    if len(columns) < 2 or not on_story_walk(task, utils_sortie):
        return False
    if any(word in (box.name or "").casefold() for _, boxes in columns for box in boxes for word in CARD_TYPE_WORDS):
        return False
    hints = [box for box in task.all_texts or [] if in_region(box, HINT_REGION, task.width, task.height)
             and 2 < len((box.name or "").strip(" .…")) <= HINT_LONGEST]
    if hints:
        hint = (hints[0].x + hints[0].width / 2) / task.width
        chosen = min(columns, key=lambda column: abs(column[0] - hint))
    else:
        chosen = columns[0]
    title = chosen[1][0]
    others = [column[1][0].y for column in columns if column is not chosen]
    raised = all(title.y / task.height < other / task.height - CHOICE_RAISED for other in others)
    last = getattr(task, CHOICE_PRESSED, None)
    if last and time.monotonic() - last < CHOICE_COOLDOWN:
        return False
    pointed = f" (pointed at by '{hints[0].name.strip()}')" if hints else ""
    if raised:
        task.log_info(f"story walk card '{title.name.strip()}' raised, taking it{pointed}")
        task.click_relative(chosen[0], CHOICE_TAKE_Y)
    else:
        task.log_info(f"story walk offers {len(columns)} cards, raising '{title.name.strip()}'{pointed}")
        task.click_box(title)
    setattr(task, CHOICE_PRESSED, time.monotonic())
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
    # Any stage text at the edge, not only its number: in Chapter 3 the next stage showed just the start of its name
    # ("The B" at (0.967, 0.436)) with the number cut off, and the map stood still for three minutes.
    edge = next((box for box in texts
                 if ((box.name or "").strip().startswith("#") or len((box.name or "").strip()) >= 2)
                 and in_region(box, EDGE_STAGE_REGION, width, height)), None)
    # An unentered chaos stage anywhere on the map comes first: dragging away from it left the two drags alternating.
    if not on_map or edge is None or any(OBSERVE_STEM in (box.name or "").casefold() for box in texts):
        return False
    search = task.box_of_screen(*MAP_REGION)
    if any(task.find_feature(feature_name="enterstory", box=search) or []):
        return False
    last = getattr(task, MAP_DRAG_PRESSED, None)
    if last and time.monotonic() - last < OPTION_COOLDOWN:
        return False
    task.log_info(f"next stage cut off at the map's right edge ('{edge.name.strip()}'), dragging the map left")
    (x1, y1), (x2, y2) = MAP_DRAG
    drag_map(task, x1, y1, x2, y2)
    setattr(task, MAP_DRAG_PRESSED, time.monotonic())
    task.sleep(1)
    return True


def drag_map(task, x1, y1, x2, y2):
    """Drag the story map by exactly the distance given, with no fling after the drag."""
    task.swipe_relative(x1, y1, x2, y2, duration=MAP_DRAG_SECONDS, settle_time=MAP_DRAG_HOLD)


def handle_map_drag_back(task, utils_sortie=None):
    """Drag the map back once when a drag left it with nothing to enter and nothing past its right edge.

    Returns:
        True when the map was dragged back.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    texts = task.all_texts or []
    on_map = any((box.name or "").strip().casefold().startswith("chapter")
                 and in_region(box, CHAPTER_TABS_REGION, width, height) for box in texts)
    if not on_map or titled(task, BATTLE_MISSIONS):
        return False
    dragged = getattr(task, MAP_DRAG_PRESSED, None)
    back = getattr(task, MAP_DRAG_BACK_PRESSED, None)
    if not dragged or (back and back > dragged) or time.monotonic() - dragged > MAP_DRAG_BACK_WITHIN:
        return False
    if time.monotonic() - dragged < MAP_SETTLE_SECONDS:
        return False
    if any(in_region(box, EDGE_STAGE_REGION, width, height) for box in texts):
        return False
    if any(OBSERVE_STEM in (box.name or "").casefold() for box in texts):
        return False
    search = task.box_of_screen(*MAP_REGION)
    if any(task.find_feature(feature_name="enterstory", box=search) or []):
        return False
    task.log_info("the drag left nothing to enter on the map, dragging it back")
    (x1, y1), (x2, y2) = MAP_DRAG_BACK
    drag_map(task, x1, y1, x2, y2)
    setattr(task, MAP_DRAG_BACK_PRESSED, time.monotonic())
    task.sleep(1)
    return True


MAP_DRAG_BACK_WITHIN = 90


def handle_chapter_forward(task, utils_sortie=None):
    """Go to the next chapter by the tab bar's arrow once a map has nothing left to enter and nothing past its edge.

    Returns:
        True when the arrow was pressed.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    texts = task.all_texts or []
    on_map = any((box.name or "").strip().casefold().startswith("chapter")
                 and in_region(box, CHAPTER_TABS_REGION, width, height) for box in texts)
    if not on_map or titled(task, BATTLE_MISSIONS):
        return False
    if any(in_region(box, EDGE_STAGE_REGION, width, height) for box in texts):
        return False
    if any(OBSERVE_STEM in (box.name or "").casefold() for box in texts):
        return False
    search = task.box_of_screen(*MAP_REGION)
    if any(task.find_feature(feature_name="enterstory", box=search) or []):
        return False
    last = getattr(task, CHAPTER_FORWARD_PRESSED, None)
    if last and time.monotonic() - last < CHAPTER_FORWARD_COOLDOWN:
        return False
    task.log_info("nothing left on this chapter's map and no next chapter shown on it, backing out to pick the next")
    task.click_relative(*CHAPTER_FORWARD)
    setattr(task, CHAPTER_FORWARD_PRESSED, time.monotonic())
    task.sleep(2)
    return True


# The screen backing out of a finished chapter lands on: a Story card naming the next episode ("Act 4 - Chapter 1,
# Episode 1") beside a Battle Missions card (snapshot 20261011-220855). Upstream's stage-entrance match clicked the
# Battle Missions card, and the run wandered between that map and this screen.
BATTLE_MISSIONS = "battle missions"
HUB_CARDS_REGION = (0.0, 0.60, 1.0, 1.0)
EPISODE_WORD = "episode"
HUB_PRESSED = "_en_story_hub_pressed"
HUB_COOLDOWN = 10
OFF_PATH_PRESSED = "_en_off_path_pressed"
OFF_PATH_COOLDOWN = 5


def titled(task, title):
    """Whether the screen's top-left title reads `title`."""
    from src.en.screen import in_region

    return any((box.name or "").strip().casefold() == title
               and in_region(box, STORY_LABEL_REGION, task.width, task.height) for box in task.all_texts or [])


def handle_story_hub(task, utils_sortie=None):
    """Open the next story episode from the screen with the Story and Battle Missions cards.

    Returns:
        True when the Story card was pressed.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    lower = [box for box in task.all_texts or [] if in_region(box, HUB_CARDS_REGION, width, height)]
    episode = next((box for box in lower if EPISODE_WORD in (box.name or "").casefold()), None)
    if episode is None or not any(BATTLE_MISSIONS in (box.name or "").casefold() for box in lower):
        return False
    last = getattr(task, HUB_PRESSED, None)
    if last and time.monotonic() - last < HUB_COOLDOWN:
        return False
    task.log_info(f"on the story screen, opening the next episode '{episode.name.strip()}'")
    task.click_box(episode)
    setattr(task, HUB_PRESSED, time.monotonic())
    task.sleep(2)
    return True


# The Story card opens a list of acts, each card with its name and "Complete" under it once done; the next act's card
# shows the chapter and episode to play instead (snapshot 20261011-221018: Act 1-3 Complete, Act 4 "Chapter 1 Episode").
ACT_TITLES_REGION = (0.0, 0.60, 1.0, 0.70)
ACT_CARDS_REGION = (0.0, 0.70, 1.0, 0.90)
ACT_COLUMN = 0.06
COMPLETE_WORD = "complete"
ACT_PRESSED = "_en_act_pressed"


def handle_act_list(task, utils_sortie=None):
    """Open the first act whose card is not marked Complete.

    Returns:
        True when an act's card was pressed.
    """
    from src.en.screen import in_region

    width, height = task.width, task.height
    texts = task.all_texts or []
    acts = sorted((box for box in texts if (box.name or "").replace(" ", "").casefold().startswith("act")
                   and in_region(box, ACT_TITLES_REGION, width, height)), key=lambda box: box.x)
    if len(acts) < 2:
        return False
    cards = [box for box in texts if in_region(box, ACT_CARDS_REGION, width, height)]

    def column(act):
        middle = (act.x + act.width / 2) / width
        return [box for box in cards if abs((box.x + box.width / 2) / width - middle) < ACT_COLUMN]

    act = next((act for act in acts
                if not any(COMPLETE_WORD in (box.name or "").casefold() for box in column(act))), None)
    if act is None:
        return False
    last = getattr(task, ACT_PRESSED, None)
    if last and time.monotonic() - last < HUB_COOLDOWN:
        return False
    target = max(column(act), key=lambda box: box.y, default=act)
    task.log_info(f"on the act list, opening '{act.name.strip()}', the first not marked Complete")
    task.click_box(target)
    setattr(task, ACT_PRESSED, time.monotonic())
    task.sleep(2)
    return True


def handle_off_story_path(task, utils_sortie=None):
    """Back out of the Battle Missions map, which the Story mode has no business on.

    Returns:
        True when the back button was pressed.
    """
    if not titled(task, BATTLE_MISSIONS):
        return False
    last = getattr(task, OFF_PATH_PRESSED, None)
    if last and time.monotonic() - last < OFF_PATH_COOLDOWN:
        return False
    task.log_info("on the Battle Missions map instead of the story, backing out")
    task.click_relative(*CHAPTER_FORWARD)
    setattr(task, OFF_PATH_PRESSED, time.monotonic())
    task.sleep(2)
    return True


def handle_observe_stage(task, utils_sortie=None):
    """Enter a chaos stage from the story map and hand its run to the Chaos mode.

    Args:
        task: The running task.
        utils_sortie: Unused; every step takes the same arguments.

    Returns:
        True when the stage was entered.
    """
    from src.en.screen import in_region

    stage = next((box for box in task.all_texts or [] if (box.name or "").strip().casefold() == OBSERVE
                  and in_region(box, OBSERVE_REGION, task.width, task.height)), None)
    if stage is None:
        return False
    return enter_observe(task, stage, "chaos stage on the story map, entering it and handing the run to the Chaos mode")


def enter_observe(task, stage, message):
    """Click a chaos stage on the story map and hand its run to the Chaos mode.

    Returns:
        True when the stage was clicked.
    """
    from src.en import autostart

    # A dragged map slides on for a moment: the click two seconds after a drag landed where the stage had been.
    dragged = max(getattr(task, MAP_DRAG_PRESSED, None) or 0, getattr(task, MAP_DRAG_BACK_PRESSED, None) or 0)
    if dragged and time.monotonic() - dragged < MAP_SETTLE_SECONDS:
        return False
    last = getattr(task, OBSERVE_PRESSED, None)
    if last and time.monotonic() - last < 30:
        return False
    task.log_info(message)
    task.click_box(stage)
    setattr(task, OBSERVE_PRESSED, time.monotonic())
    task.sleep(4)
    autostart.request_switch("ChaosMode", then_story=True)
    return True


# Act 4 Chapter 1: the chaos stage stood cut off at the map's left edge ("Observe" read at (0.027, 0.505), its first
# letter off screen) with #09 locked after it, and the run dragged the map left and backed out of the chapter instead
# (snapshot 20261011-222128).
OBSERVE_EDGE_REGION = (0.0, 0.35, 0.092, 0.70)
OBSERVE_STEM = "bserve"
MAP_DRAG_BACK_PRESSED = "_en_map_drag_back_pressed"
MAP_SETTLE_SECONDS = 4


def observe_at_left_edge(task):
    """The chaos stage's label cut off at the map's left edge, if it is."""
    from src.en.screen import in_region

    return next((box for box in task.all_texts or [] if OBSERVE_STEM in (box.name or "").casefold()
                 and in_region(box, OBSERVE_EDGE_REGION, task.width, task.height)), None)


def handle_observe_cut_off(task, utils_sortie=None):
    """Enter the chaos stage where it is cut off at the map's left edge, by the part of it still on screen.

    Dragging the map right to it flung the map back to its start (snapshot 20261011-222330: Prologue on screen), and
    the drag left from there flung it past the stage again.

    Returns:
        True when the stage was entered.
    """
    stage = observe_at_left_edge(task)
    if stage is None:
        return False
    return enter_observe(task, stage, "chaos stage cut off at the map's left edge, entering it by what shows")


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
    ruled = True
    for top, bottom in BOX_RULES:
        rows = [grey[y, columns].mean() for y in range(int(top * height), int(bottom * height))]
        if not rows or max(rows) - float(np.median(rows)) < BOX_RULE_CONTRAST:
            ruled = False
            break
    if ruled:
        inside = grey[int(BOX_INSIDE[0] * height):int(BOX_INSIDE[1] * height), columns]
        if float(inside.mean()) < BOX_INSIDE_DARK:
            return True
    return dark_band_on_bright_scene(grey, columns, height)


def dark_band_on_bright_scene(grey, columns, height):
    """Say whether the box stands as a dark band against a bright scene, with no rule drawn along its edges.

    Act 4 Chapter 3's box sat on a sky: rows at 213 above and below, 42 inside, the line's text lifting the inside's
    mean to 50 (snapshot 20261011-232427), so neither the rule test nor the dark-inside test held.
    """
    import numpy as np

    for top, bottom in BOX_RULES:
        rows = [grey[y, columns].mean() for y in range(int(top * height), int(bottom * height))]
        if not rows or max(rows) - min(rows) < BOX_EDGE_STEP:
            return False
    inside = [grey[y, columns].mean() for y in range(int(BOX_INSIDE[0] * height), int(BOX_INSIDE[1] * height))]
    return bool(inside) and float(np.median(inside)) < BOX_BAND_DARK


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
    # Text in the box's corner is not enough on its own: the status-effect panel writes there too ("Chronal
    # Ascension" was clicked eight times running). Where a frame is to hand, the box's own frame has to be seen.
    frame = getattr(task, "frame", None)
    if frame is not None and not speech_box_on_screen(frame):
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
LEFT_MAP_FOR = "_en_left_story_map_for"
# A chaos stage that never opened still hands back, after this long on the map.
STILL_ON_MAP_SECONDS = 120
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

    marker = status_folder() / autostart.RETURN_NAME
    if not marker.exists() or getattr(task, "name", "") == "半自动剧情模式":
        return False
    texts = task.all_texts or []
    labelled = any((box.name or "").strip().casefold() in STORY_LABELS
                   and in_region(box, STORY_LABEL_REGION, task.width, task.height) for box in texts)
    chapter = any((box.name or "").strip().casefold().startswith("chapter")
                  and in_region(box, CHAPTER_TABS_REGION, task.width, task.height) for box in texts)
    try:
        written = marker.stat().st_mtime
    except OSError:
        return False
    if not (labelled and chapter):
        setattr(task, LEFT_MAP_FOR, written)
        return False
    # Only once the run has left the map for the stage: Act 4's chaos stage opened a panel over the map first, and the
    # Chaos mode handed straight back before pressing its Enter, leaving the Story mode inside a run it cannot play.
    if getattr(task, LEFT_MAP_FOR, None) != written and time.time() - written < STILL_ON_MAP_SECONDS:
        return False
    task.log_info("back on the story map after the chaos stage, handing back to the Story mode")
    (status_folder() / autostart.RETURN_NAME).unlink(missing_ok=True)
    autostart.request_switch("StoryMode")
    task.sleep(3)
    return True


def status_folder():
    from src.en import status
    return status.PATH.parent


EFFECT_TITLE = "effect"
EFFECT_TITLE_REGION = (0.08, 0.02, 0.25, 0.09)
HEALTH_REGION_PANEL = (0.60, 0.02, 0.93, 0.09)
PANEL_CLOSE = (0.960, 0.052)


SAVE_TARGET_STATUS = "save_target_member"


def handle_story_chaos_run(task, utils_sortie=None):
    """Skip the save-target avatar lookup in a chaos stage the Story mode handed over.

    The lookup taps the main combatant's portrait for the statistics page. In Act 4's story chaos stage, with the
    story's own party, that tap opened the status-effect panel instead, which was closed and tapped open again every
    five seconds. A story stage farms no save data, so the lookup is marked done.

    Returns:
        False always: it only changes what upstream's handler sees.
    """
    from src.en import autostart

    status = getattr(task, "node_status", None)
    if not isinstance(status, dict) or status.get(SAVE_TARGET_STATUS):
        return False
    if not (status_folder() / autostart.RETURN_NAME).exists() or getattr(task, "name", "") == "半自动剧情模式":
        return False
    status[SAVE_TARGET_STATUS] = True
    task.log_info("chaos stage handed over by the Story mode, skipping the save-target avatar lookup")
    return False


def handle_walk_magnifier(task, utils_sortie=None):
    """Look at a walk scene's magnifiers in a chaos stage the Story mode handed over.

    Act 4's story chaos stage opened on a walk scene with two magnifiers, and the Chaos mode, which has no magnifier
    handler, tapped the narration line for three minutes (snapshot 20261011-223222). Only in a handed-over run, so a
    Chaos run of its own pays nothing for the template match.

    Returns:
        True when a magnifier was clicked.
    """
    from src.en import autostart

    if not (status_folder() / autostart.RETURN_NAME).exists() or getattr(task, "name", "") == "半自动剧情模式":
        return False
    return magnifier_step(lambda _task: False, task)


def handle_effect_panel(task, utils_sortie=None):
    """Close the status-effect panel a stray tap opened mid-fight ("Effect" top left, "Health 1870(94.5%)" top right).

    Returns:
        True when it was closed.
    """
    from src.en.screen import in_region

    texts = task.all_texts or []
    title = any((box.name or "").strip().casefold() == EFFECT_TITLE
                and in_region(box, EFFECT_TITLE_REGION, task.width, task.height) for box in texts)
    health = any("health" in (box.name or "").casefold()
                 and in_region(box, HEALTH_REGION_PANEL, task.width, task.height) for box in texts)
    if not (title and health):
        return False
    task.log_info("status-effect panel open, closing it")
    task.click_relative(*PANEL_CLOSE)
    task.sleep(1)
    return True


def handle_fork_steps(task, utils_sortie=None):
    """Run the steps this fork adds to the Chaos and Sortie modes, first that answers wins; reloadable like Story's."""
    for step in GENERAL_STEPS:
        try:
            if globals()[step](task, utils_sortie):
                return True
        except Exception as error:
            logger.error(f"step {step} failed: {error!r}", exception=error)
    return False


GENERAL_STEPS = ("handle_story_chaos_run", "handle_walk_magnifier", "handle_touch_to_start", "handle_chaos_reconnect", "handle_effect_panel", "handle_back_on_story_map",
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
STORY_STEPS = ("handle_touch_to_start", "handle_chaos_reconnect", "handle_effect_panel", "handle_stage_complete", "handle_fight_first", "handle_pile_pick", "handle_walk_choice", "walk_dialogue_step", "handle_observe_stage", "handle_observe_cut_off", "handle_next_chapter",
               "handle_story_hub", "handle_act_list", "handle_off_story_path", "handle_map_drag", "handle_map_drag_back", "handle_chapter_forward")


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


# In the Story list the skip box goes ahead of the skip button: Act 4's box leaves the button visible above it, and
# upstream pressed the button again every two seconds while the box waited (snapshot 20261011-221553).
SKIP_ANCHOR = "handle_skip_story"


def place_skip_confirm():
    """Put the skip-box confirm ahead of the skip button in the Story list, ahead of the confirm handler elsewhere."""
    insert_before(SKIP_ANCHOR, proxy(__name__, handle_skip_dialogue_confirm.__name__))
    insert_before(CONFIRM_ANCHOR, proxy(__name__, handle_skip_dialogue_confirm.__name__))


def install():
    """Wrap the Story stage handler once both modules are loaded."""
    utils, utils_story = loaded("utils"), loaded("utils_story")
    if utils is None or utils_story is None:
        return
    wrap(utils_story, "handle_enter_stage", lambda original: pressing_enter(original, utils), TAG)
    place_skip_confirm()
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
