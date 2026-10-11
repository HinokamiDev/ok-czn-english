"""Play a Story fight with the Sortie card player when the game's Auto is not playing it.

Upstream's Story mode only switches the game's Auto on, and on the Global client it cannot even tell whether Auto
is on - the pixel it reads is dark either way - so a Story fight without Auto sat on the player's turn until
someone played it by hand, or started Sortie mode for it. This watches the fight instead: once it is the player's
turn and the hand has not changed for a while, nobody is playing, and the Sortie card player takes the fight over
until it ends. A fight Auto is playing changes the hand every few seconds and is left alone.
"""

import time

from ok import Logger

from src.en.handlers import each_list, loaded, register
from src.en.live import proxy

logger = Logger.get_logger(__name__)

# How long the player's turn has to sit with an unchanged hand before the fight is taken over.
IDLE_SECONDS = 12
# How long the hand counter can be gone before the fight counts as over. A box over the fight hides the counter, and
# 10s handed a fight back while the game was still asking about ending the turn.
FIGHT_OVER_SECONDS = 30
# The game's question when a turn is ended with playable cards, and its two buttons. Read live (20261011-200656):
# question at (0.5, 0.358), Cancel at (0.347, 0.604), Confirm at (0.667, 0.604). The Story list has no handler for it.
CARDS_LEFT = "can still be used"
CARDS_LEFT_REGION = (0.15, 0.25, 0.85, 0.50)
CANCEL, CONFIRM = "取消", "确认"
BUTTON_REGION = (0.15, 0.52, 0.85, 0.70)
# Set by the walk-dialogue handler when it clicks a speech box on.
DIALOGUE_PRESSED = "_en_story_walk_dialogue_pressed"
CARDS_LEFT_CANCELLED = "_en_story_cards_left_cancelled"
ANCHOR = "handle_battle_auto_check"
SORTIE_PLAYER = "handle_battle_page"
SORTIE_OFFER = "handle_battle_card_choice"
FINISH_TURN = "finishturn"
FINISH_TURN_REGION = (0.844, 0.782, 0.998, 0.990)
# Held on the task.
STATE = "_en_story_fight"

_patched = False


def sortie_handler(name):
    """Find a handler as the Sortie mode runs it, carrying every fork change made to it.

    Args:
        name: The handler's `__name__`.

    Returns:
        The function from Sortie's own list, or None when Sortie is not loaded.
    """
    for module_name, handlers in each_list():
        if module_name == "utils_sortie":
            return next((handler for handler in handlers if getattr(handler, "__name__", None) == name), None)
    return None


def hand_of(task, utils_sortie):
    """Read the fight's hand counter, or None when no fight is on screen.

    The counter alone, not the card names: OCR reads the same hand as 2, 3 or 4 part-names from one frame to the
    next, so a name list never held still and an idle fight was never noticed. The counter read a steady 5.
    """
    return utils_sortie._read_hand_count(task)


def answer_cards_left(task, now):
    """Answer the game's question about ending a turn with cards still playable.

    Cards the game refused while a speech box was up were refused for that reason, not for being unplayable, so once
    a box has been clicked on since, the end of turn is cancelled and the refusals forgotten - once. Otherwise the
    end was chosen on purpose and is confirmed.

    Returns:
        True when the question was on screen and answered.
    """
    from src.en.battle import TURN
    from src.en.screen import text_in_region

    if text_in_region(task, CARDS_LEFT, CARDS_LEFT_REGION) is None:
        return False
    turn = getattr(task, TURN, None)
    pressed = getattr(task, DIALOGUE_PRESSED, None)
    cancelled = getattr(task, CARDS_LEFT_CANCELLED, None)
    refused_by_box = (turn is not None and turn.refused and pressed is not None
                      and (cancelled is None or pressed[1] > cancelled))
    button = text_in_region(task, CANCEL if refused_by_box else CONFIRM, BUTTON_REGION)
    if button is None:
        return False
    if refused_by_box:
        task.log_info(f"cards were refused while a speech box was up ({sorted(turn.refused)}); cancelling the end of"
                      f" turn and trying them again")
        turn.refused.clear()
        turn.misses.clear()
        setattr(task, CARDS_LEFT_CANCELLED, time.monotonic())
    else:
        task.log_info("the turn was ended on purpose with cards left, confirming")
    task.click_box(button)
    task.sleep(1)
    state = getattr(task, STATE, None)
    if state:
        state["seen"] = now
    return True


def handle_story_fight_without_auto(task, utils_sortie=None, now=None):
    """Run `taking_over`, so that a fault in it costs this frame and not the whole Story run."""
    try:
        if answer_cards_left(task, time.monotonic() if now is None else now):
            return True
        return taking_over(task, utils_sortie, now)
    except Exception as error:
        logger.error(f"could not judge whether to play this Story fight: {error}", exception=error)
        return False


def taking_over(task, utils_sortie=None, now=None):
    """Take a Story fight over once nobody is playing it.

    Args:
        task: The running Story mode.
        utils_sortie: The Sortie module, looked up when not given.
        now: The time, for tests.

    Returns:
        True when the frame was played by the Sortie card player.
    """
    utils_sortie = utils_sortie or loaded("utils_sortie")
    if utils_sortie is None:
        return False
    now = time.monotonic() if now is None else now
    state = getattr(task, STATE, None) or {"hand": None, "since": now, "seen": now, "playing": False}
    setattr(task, STATE, state)

    if state["playing"]:
        offer = sortie_handler(SORTIE_OFFER)
        if offer is not None and offer(task):
            state["seen"] = now
            return True

    hand = hand_of(task, utils_sortie)
    if hand is None:
        if state["playing"] and now - state["seen"] > FIGHT_OVER_SECONDS:
            task.log_info("the fight is over, handing back to the Story mode")
            setattr(task, STATE, None)
        return False
    state["seen"] = now

    if not state["playing"]:
        if hand != state["hand"]:
            state["hand"], state["since"] = hand, now
            return False
        if now - state["since"] < IDLE_SECONDS:
            return False
        if not task.find_feature(feature_name=FINISH_TURN, box=task.box_of_screen(*FINISH_TURN_REGION)):
            return False
        task.log_info(f"no card played for {int(now - state['since'])}s on the player's turn, so Auto is not playing"
                      f" this fight; the Sortie card player takes it over")
        state["playing"] = True

    player = sortie_handler(SORTIE_PLAYER)
    if player is None:
        task.log_info("the Sortie card player is not loaded, so this fight is left as it is")
        return False
    return bool(player(task))


def apply():
    """Let the Story mode play the fights the game's Auto does not."""
    global _patched
    if _patched:
        return

    def install():
        # Only the Story list carries the anchor without also carrying Sortie's own fight handler.
        for module_name, handlers in each_list():
            if module_name == "utils_story":
                if not any(getattr(handler, "__name__", None) == handle_story_fight_without_auto.__name__
                           for handler in handlers):
                    # By prefix: `observe.py` renames the anchor when it wraps it for recording.
                    index = next((i for i, handler in enumerate(handlers)
                                  if str(getattr(handler, "__name__", "")).startswith(ANCHOR)), len(handlers))
                    handlers.insert(index, proxy(__name__, handle_story_fight_without_auto.__name__))
                    logger.info(f"utils_story: {handle_story_fight_without_auto.__name__} inserted at {index}")

    register(install)
    _patched = True
