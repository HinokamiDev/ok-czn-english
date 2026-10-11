"""Answer the card pick a card opens mid-fight, instead of leaving it to the stuck fallback.

Some cards open a screen of their own when played: Nia's Curiosity shows three cards from the Draw Pile to draw
one of, and other variants of Nia's cards ask for one to discard instead. No Sortie handler knows those screens, so
the fight sat on them for ten seconds until upstream's stuck fallback clicked one of the cards at random. This reads
the screen's own prompt, outside the cards, to tell the two apart: a card to keep takes the one the Smart Card Play
valuation rates highest, a card to discard the one it rates lowest. A prompt that says neither, or both, is left
alone and written to the log, so the wording can be added rather than guessed.
"""

from ok import Logger

from src.en import cards
from src.en.battle import TURN
from src.en.handlers import append, loaded, register
from src.en.live import proxy

logger = Logger.get_logger(__name__)

# The handler the Sortie fight runs through. Appending after every handler keeps this to frames nothing else claimed.
ANCHOR = "handle_battle_page"
# Where the offered cards sit: the large three-card layout, well above the hand.
OFFER_TOP, OFFER_BOTTOM = 0.15, 0.60
# Held on the task: the offer seen on the previous frame, so a pick waits for a settled screen.
LAST_OFFER = "_en_battle_offer"
PAGE = "battle card choice"
# The prompt sits above or below the cards. Text inside the band is the cards' own, whose effects say Draw and
# Discard too, so it is left out.
PROMPT_ABOVE, PROMPT_BELOW = 0.22, 0.84
DISCARD_WORDS = ("discard",)
KEEP_WORDS = ("draw", "hand", "obtain", "acquire")

_patched = False


def offer_of(found):
    """Keep the cards that sit where a mid-fight offer lays them out.

    Args:
        found: Cards from `recognize_cards`.

    Returns:
        The cards in the offer band, left to right.
    """
    return sorted((card for card in found if OFFER_TOP <= card["y"] <= OFFER_BOTTOM), key=lambda card: card["x"])


def prompt_of(task):
    """Read the text around the offer, where the screen says what the pick is for.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        The prompt's text, lower-cased.
    """
    lines = []
    for box in task.all_texts or []:
        center_y = (box.y + box.height / 2) / task.height
        if center_y < PROMPT_ABOVE or center_y > PROMPT_BELOW:
            lines.append(box.name)
    return " ".join(lines).casefold()


def intent_of(prompt):
    """Say whether the pick keeps a card or throws one away.

    Args:
        prompt: The prompt's text, lower-cased.

    Returns:
        "keep", "discard", or None when the prompt says neither or both.
    """
    discard = any(word in prompt for word in DISCARD_WORDS)
    keep = any(word in prompt for word in KEEP_WORDS)
    if discard and not keep:
        return "discard"
    if keep and not discard:
        return "keep"
    return None


def worst_of(offer):
    """Pick the card worth least to the fight.

    Args:
        offer: The cards on offer.

    Returns:
        The weakest card, the leftmost on a tie.
    """
    board = cards.Board()
    return min(offer, key=lambda card: (cards.value(cards.canonical(card["name"]), board), card["x"]))


def best_of(offer):
    """Pick the card worth most to the fight.

    Args:
        offer: The cards on offer.

    Returns:
        The best card, the leftmost on a tie.
    """
    board = cards.Board()
    return max(offer, key=lambda card: (cards.value(cards.canonical(card["name"]), board), -card["x"]))


def handle_battle_card_choice(task, utils=None):
    """Pick from a card offer a card opened mid-fight.

    Args:
        task: The running task.
        utils: The module holding the recognizer and the click, looked up when not given.

    Returns:
        True when the frame was an offer and was handled.
    """
    if getattr(task, TURN, None) is None:
        return False
    utils = utils or loaded("utils")
    if utils is None:
        return False
    offer = offer_of(utils.recognize_cards(task, page=PAGE) or [])
    if not 2 <= len(offer) <= 3:
        setattr(task, LAST_OFFER, None)
        return False
    names = [card["name"] for card in offer]
    if getattr(task, LAST_OFFER, None) != names:
        # Seen once: wait a frame, so a card sweeping across the screen is not taken for an offer.
        setattr(task, LAST_OFFER, names)
        return True
    prompt = prompt_of(task)
    intent = intent_of(prompt)
    if intent is None:
        task.log_info(f"mid-fight card offer {names} with a prompt that says neither keep nor discard: {prompt!r}")
        setattr(task, LAST_OFFER, None)
        return False
    pick = best_of(offer) if intent == "keep" else worst_of(offer)
    task.log_info(f"mid-fight card offer {names} to {intent} ({prompt!r}), taking {pick['name']}")
    utils._move_and_click(task, pick["x"], pick["y"])
    setattr(task, LAST_OFFER, None)
    task.sleep(1)
    return True


def apply():
    """Answer mid-fight card offers in the modes that play their own fights."""
    global _patched
    if _patched:
        return
    register(lambda: append(proxy(__name__, handle_battle_card_choice.__name__), ANCHOR))
    _patched = True
