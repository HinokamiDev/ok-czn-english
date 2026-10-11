"""Keep card picks to what the user listed, and hand back control rather than guess.

Upstream fills every gap in the priority lists with a guess. An Epiphany nothing in Epiphany Priority matches is
picked with `random.choice`, and the in-game target marker is clicked ahead of a priority that did match. A copy
is matched on the card's name alone, so the wrong Epiphany variant is copied as readily as the right one, and as
many times as the run offers. Remove Basic Cards First removes any basic card, a combatant's basic healing cards
included. This module closes those gaps, and leaves each one switchable back to upstream's behaviour.
"""

import re

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap

logger = Logger.get_logger(__name__)

# Settings this module adds. English keys, like the rest of the fork's own settings.
UNMATCHED_EPIPHANY = "Unmatched Epiphany"
PAUSE_LISTED = "Pause on listed cards"
PAUSE_ALWAYS = "Always pause"
RANDOM = "Random (upstream)"
UNMATCHED_CHOICES = [PAUSE_LISTED, PAUSE_ALWAYS, RANDOM]
STRICT_MATCHING = "Strict Epiphany Matching"
MAX_COPIES = "Max Copies Per Card"
COPY_ONLY_PRIORITISED = "Copy Only Prioritised Epiphany"
NEVER_REMOVE = "Never Remove"
DEFAULTS = {
    UNMATCHED_EPIPHANY: PAUSE_LISTED,
    STRICT_MATCHING: True,
    MAX_COPIES: 4,
    COPY_ONLY_PRIORITISED: True,
    NEVER_REMOVE: [],
}
DESCRIPTIONS = {
    UNMATCHED_EPIPHANY: "What to do when an Epiphany matches nothing in Epiphany Priority and shows no target marker."
                        " Pause on listed cards stops only for a card named in the Epiphany, Copy or Epiphany"
                        " Priority lists, so you pick its variant yourself and press Resume.",
    STRICT_MATCHING: "Each word of an Epiphany Priority entry has to appear, in order, in the card's name and"
                     " description. Off, the letters only have to appear in order, which can match the wrong variant.",
    MAX_COPIES: "Most copies of one card the deck may hold, counting the original. 0 removes the limit.",
    COPY_ONLY_PRIORITISED: "When Epiphany Priority has an entry for a card, only copy that card once it carries"
                           " the matching variant.",
    NEVER_REMOVE: "Cards no removal may take, matched word by word against name and description, so Heal keeps"
                  " every healing card.",
}
# Marks the modes that choose cards, which are the ones these settings belong on.
ANCHOR_SETTING = "复制卡牌列表"

# Upstream's config keys and page names.
EPIPHANY_PRIORITY = "闪光优先级"
EPIPHANY_CARDS = "闪光卡牌列表"
COPY_CARDS = "复制卡牌列表"
EPIPHANY_PAGE = "卡牌闪光页面"
COPY_PAGE = "复制卡牌选择页面"
COPY = "复制"
REMOVE = "移除"
# Where the copies made this run are counted. `member_status` is replaced at the start of every run.
COPIES_KEY = "_en_copies"
# Names each change in the shared record of what a function already carries.
EPIPHANY_TAG = "safe epiphany"
DECK_TAG = "safe deck picks"
COPY_CHOICE_TAG = "safe copy choice"

_patched = False


def squash(text):
    """Drop whitespace and case, which OCR does not read reliably.

    Args:
        text: Any string, or None.

    Returns:
        The squashed string.
    """
    return re.sub(r"\s+", "", text or "").lower()


def card_text(card):
    """Join a card's name and description the way upstream does before matching.

    Args:
        card: A card dict from a recognizer.

    Returns:
        The combined text.
    """
    return f"{card.get('name') or ''}：:{card.get('description') or ''}"


def words_match(entry, text):
    """Check that every word of an entry appears in the text, in order.

    Each word has to be a real run of characters in the text, unlike upstream's subsequence test, where the
    letters of "Retain Extra Attack" can be picked out of a description that says something else entirely.

    Args:
        entry: The configured entry, words separated by spaces.
        text: The text to search.

    Returns:
        True when every word was found in order.
    """
    words = [squash(word) for word in (entry or "").split()]
    words = [word for word in words if word]
    if not words:
        return False
    haystack = squash(text)
    position = 0
    for word in words:
        found = haystack.find(word, position)
        if found < 0:
            return False
        position = found + len(word)
    return True


def config(task, utils, key):
    """Read one of this module's settings, falling back to its default.

    Args:
        task: The running task.
        utils: The module holding `_get_config_value`.
        key: The setting.

    Returns:
        The configured value.
    """
    return utils._get_config_value(task, key, DEFAULTS[key])


def entry_list(task, utils, key):
    """Read a list setting as its non-empty strings.

    Args:
        task: The running task.
        utils: The module holding `_get_card_list`.
        key: The setting.

    Returns:
        The stripped entries.
    """
    return [entry.strip() for entry in utils._get_card_list(task, key) if isinstance(entry, str) and entry.strip()]


def names_match(listed, name):
    """Compare a listed card name with one OCR read, as loosely as upstream's own name lists do.

    Args:
        listed: The name from a setting.
        name: The name OCR read.

    Returns:
        True when either contains the other.
    """
    listed, name = squash(listed), squash(name)
    return bool(listed and name) and (listed in name or name in listed)


def entries_about(name, entries):
    """Pick the Epiphany Priority entries written for one card, which start with its name.

    Args:
        name: The card's name.
        entries: The Epiphany Priority entries.

    Returns:
        The entries that begin with that name.
    """
    key = squash(name)
    return [entry for entry in entries if key and squash(entry).startswith(key)]


def matcher(task, utils):
    """Choose how an Epiphany Priority entry is compared with a card.

    Args:
        task: The running task.
        utils: The module holding upstream's `is_subsequence`.

    Returns:
        A function of `(entry, text)`.
    """
    if config(task, utils, STRICT_MATCHING) is False:
        loose = utils.is_subsequence
        return lambda entry, text: loose(re.sub(r"\s+", "", entry), text)
    return words_match


def first_priority_match(cards, entries, matches):
    """Find the card upstream's priority loop should take: the first entry, then the first card it matches.

    Args:
        cards: The cards on screen.
        entries: The Epiphany Priority entries, best first.
        matches: The comparison to use.

    Returns:
        An `(entry, card)` pair, or None when nothing matches.
    """
    for entry in entries:
        for card in cards:
            if matches(entry, card_text(card)):
                return entry, card
    return None


def is_listed(task, utils, card):
    """Say whether the user named a card anywhere a wrong pick would cost them.

    Args:
        task: The running task.
        utils: The module holding the config readers.
        card: The card on screen.

    Returns:
        True when an Epiphany or Copy list names it, or an Epiphany Priority entry is written for it.
    """
    name = card.get("name") or ""
    if any(names_match(listed, name) for key in (EPIPHANY_CARDS, COPY_CARDS) for listed in entry_list(task, utils, key)):
        return True
    return bool(entries_about(name, entry_list(task, utils, EPIPHANY_PRIORITY)))


def on_epiphany_page(task, utils):
    """Recognise the Epiphany screen the way upstream's `handle_view_original` does.

    Args:
        task: The running task.
        utils: The module holding the OCR helpers.

    Returns:
        True when the View Original button is on screen.
    """
    labels = (utils._get_game_text(task, "查看原件"), utils._get_game_text(task, "查看之前的闪光"))
    for point in ((0.890, 0.051), (0.896, 0.131)):
        box = utils.find_box_at_point(task, *point)
        if box and any(label in box.name for label in labels):
            return True
    return False


def pause_for_pick(task, cards):
    """Hand the Epiphany back to the user instead of guessing.

    Args:
        task: The running task.
        cards: The variants on screen.
    """
    names = ", ".join(sorted({card.get("name") or "?" for card in cards}))
    message = (f"Epiphany for {names} matches nothing in Epiphany Priority. Paused: pick the variant in the game,"
               f" then press Resume.")
    try:
        from src.en.notify import announce
        announce(task, message, kind="takildi")
    except Exception as error:
        logger.warning(f"could not announce the Epiphany pause: {error}")
        task.log_info(message)
    pause = getattr(task, "pause", None)
    if callable(pause):
        pause()


def guarding_epiphany(handle_view_original, utils):
    """Wrap `handle_view_original` so a matched priority wins and an unmatched listed card is not guessed.

    Upstream runs unchanged over a fixed answer: the cards already read, the target marker hidden when a
    priority matched, and its subsequence test answering only for the pick made here.

    Args:
        handle_view_original: The handler to wrap, upstream's or another patch's.
        utils: The module the handler reads its helpers from.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        if not on_epiphany_page(task, utils):
            return handle_view_original(task)
        cards = utils.recognize_cards(task, page=EPIPHANY_PAGE)
        if not cards:
            return handle_view_original(task)
        entries = entry_list(task, utils, EPIPHANY_PRIORITY)
        matches = matcher(task, utils)
        hit = first_priority_match(cards, entries, matches)
        find_target_card = utils.find_target_card

        if hit is None:
            policy = config(task, utils, UNMATCHED_EPIPHANY)
            if policy != RANDOM and not find_target_card(task)[0]:
                if policy == PAUSE_ALWAYS or any(is_listed(task, utils, card) for card in cards):
                    pause_for_pick(task, cards)
                    return True

        def same_cards(*args, **kwargs):
            return cards

        def target_unless_matched(task_):
            return ([], []) if hit else find_target_card(task_)

        def only_the_pick(keyword, text):
            return bool(hit) and keyword == re.sub(r"\s+", "", hit[0]) and text == card_text(hit[1])

        if hit:
            logger.info(f"Epiphany Priority '{hit[0]}' matches {hit[1].get('name')}, which outranks any target marker")
        with standing_in(utils, recognize_cards=same_cards, find_target_card=target_unless_matched,
                         is_subsequence=only_the_pick):
            return handle_view_original(task)

    return wrapped


def copies_made(task):
    """The copies made this run, by squashed card name.

    Args:
        task: The running task.

    Returns:
        A dict, held on the run's `member_status` so a new run starts from nothing.
    """
    holder = getattr(task, "member_status", None)
    if not isinstance(holder, dict):
        holder = task.__dict__.setdefault("_en_member_status", {})
    return holder.setdefault(COPIES_KEY, {})


def copy_allowed(task, utils, card, cards, reason=None):
    """Decide whether a listed card may be copied: the right variant, and not past the copy limit.

    Args:
        task: The running task.
        utils: The module holding the config readers.
        card: The candidate.
        cards: Every card on the same screen, to count copies already visible.
        reason: A list collecting why a card was refused, for the log.

    Returns:
        True when copying it is fine. A card no Copy entry names is always allowed, as upstream allows it.
    """
    name = card.get("name") or ""
    if not any(names_match(listed, name) for listed in entry_list(task, utils, COPY_CARDS)):
        return True
    limit = config(task, utils, MAX_COPIES)
    if isinstance(limit, int) and limit > 0:
        visible = sum(1 for other in cards if squash(other.get("name")) == squash(name))
        held = max(visible, 1 + copies_made(task).get(squash(name), 0))
        if held >= limit:
            if reason is not None:
                reason.append(f"{name} already has {held} of {limit}")
            return False
    if config(task, utils, COPY_ONLY_PRIORITISED) is not False:
        wanted = entries_about(name, entry_list(task, utils, EPIPHANY_PRIORITY))
        matches = matcher(task, utils)
        if wanted and not any(matches(entry, card_text(card)) for entry in wanted):
            if reason is not None:
                reason.append(f"{name} is not yet the variant Epiphany Priority asks for")
            return False
    return True


def kept_from_removal(task, utils, card):
    """Say whether Never Remove protects a card.

    Args:
        task: The running task.
        utils: The module holding the config readers.
        card: The candidate.

    Returns:
        True when an entry matches its name and description.
    """
    return any(words_match(entry, card_text(card)) for entry in entry_list(task, utils, NEVER_REMOVE))


def record_copy(task, card):
    """Count one copy of a card against this run.

    Args:
        task: The running task.
        card: The card copied.
    """
    made = copies_made(task)
    key = squash(card.get("name"))
    made[key] = made.get(key, 0) + 1
    logger.info(f"copied {card.get('name')}, {made[key]} copy(ies) this run")


def guarding_deck(select_card, utils):
    """Wrap `select_card` so a copy honours variant and limit, and a removal spares Never Remove.

    The refused cards are simply not handed to upstream, so its priority pass, its basic-card pass and its
    fallback all pick from what is left, and it presses Skip or Cancel when nothing is.

    Args:
        select_card: The function to wrap, upstream's or another patch's.
        utils: The module holding `recognize_cards_in_deck`.

    Returns:
        The wrapped function.
    """
    def wrapped(task, card_names, count=1, action=""):
        if action not in (COPY, REMOVE):
            return select_card(task, card_names, count=count, action=action)
        original = utils.recognize_cards_in_deck
        offered = []

        def allowed(*args, **kwargs):
            cards = original(*args, **kwargs)
            kept = []
            for card in cards:
                reason = []
                if action == COPY and not copy_allowed(task, utils, card, cards, reason):
                    task.log_info(f"not copying: {'; '.join(reason)}")
                    continue
                if action == REMOVE and kept_from_removal(task, utils, card):
                    task.log_info(f"Never Remove keeps {card.get('name')}")
                    continue
                kept.append(card)
            offered.extend(card for card in kept if not card.get("selected"))
            return kept

        with standing_in(utils, recognize_cards_in_deck=allowed):
            result = select_card(task, card_names, count=count, action=action)
        if action == COPY:
            for card in offered:
                if card.get("selected"):
                    record_copy(task, card)
        return result

    return wrapped


def guarding_copy_choice(handle_copy_card_choice, utils):
    """Wrap the three-card copy screen so it honours variant and limit, and a match outranks the target marker.

    Args:
        handle_copy_card_choice: The handler to wrap, upstream's or another patch's.
        utils: The module the handler reads its helpers from.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original_recognise = utils.recognize_cards
        find_target_card = utils.find_target_card
        seen = {}

        def allowed(*args, **kwargs):
            if "cards" not in seen:
                cards = original_recognise(*args, **kwargs)
                seen["cards"] = [card for card in cards if copy_allowed(task, utils, card, cards)]
            return seen["cards"]

        def priority_pick():
            for listed in utils._get_config_value(task, COPY_CARDS, []) or []:
                for card in allowed(task, page=COPY_PAGE):
                    if card.get("name") and isinstance(listed, str) and listed in card["name"]:
                        return card
            return None

        def target_unless_matched(task_):
            return ([], []) if priority_pick() else find_target_card(task_)

        with standing_in(utils, recognize_cards=allowed, find_target_card=target_unless_matched):
            result = handle_copy_card_choice(task)
            picked = priority_pick() if result and "cards" in seen else None
        if picked is not None:
            record_copy(task, picked)
        return result

    return wrapped


def seed(task):
    """Add this module's settings to a mode that chooses cards.

    Args:
        task: The task being configured, before its `Config` exists.
    """
    if ANCHOR_SETTING not in task.default_config:
        return
    for key, value in DEFAULTS.items():
        task.default_config[key] = list(value) if isinstance(value, list) else value
        task.config_description[key] = DESCRIPTIONS[key]
    task.config_type[UNMATCHED_EPIPHANY] = {"type": "drop_down", "options": UNMATCHED_CHOICES}


def install(utils):
    """Wrap the Epiphany, deck and copy pickers wherever the run reaches them.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_view_original", lambda original: guarding_epiphany(original, utils), EPIPHANY_TAG)
    wrap(utils, "select_card", lambda original: guarding_deck(original, utils), DECK_TAG)
    wrap(utils, "handle_copy_card_choice", lambda original: guarding_copy_choice(original, utils), COPY_CHOICE_TAG)


def apply():
    """Stop guessing card picks the user has an opinion on."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
