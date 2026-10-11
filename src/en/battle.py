"""Play a Sortie battle from what the cards do, instead of pressing every hotkey and hoping.

Upstream's `handle_battle_page` plays the first hand card matching the user's Play Priority list. That list
starts empty on the Global client, so every turn falls through to `_try_all_card_keys`, which presses each
hotkey from the hand size down at about a second and a half a press - thirteen seconds of blind input at nine
cards, playing whatever sat under the last key that worked. That fallback is the only thing replaced. Upstream
keeps the frame around it, and a card the Play Priority list names is still played by upstream unchanged.
"""

import collections

from ok import Logger

from src.en import board, cards
from src.en.handlers import StandIn, insert_before, loaded, register, replace, standing_in
from src.en.overrides import SMART_CARD_PLAY
from src.en.screen import text_in_region

logger = Logger.get_logger(__name__)

# Parked on the task for the length of a battle, the way upstream parks `_play_stuck_count` and
# `_last_attempted_card`. One attribute, so starting a fresh turn is one assignment rather than three that
# have to agree. The prefix keeps it clear of anything upstream owns.
TURN = "_en_turn"
# Remembers one frame's hand reading, keyed on the OCR pass it came from. `SortieMode.run` builds a fresh
# `all_texts` list every frame, so identity tells frames apart, and a matching list can only ever produce a
# matching hand. Upstream reads the hand twice a frame already; this makes all of those one reading.
HAND_CACHE = "_en_hand_for"

# Upstream's own timings for playing a card, kept so the two paths feel the same to the game.
AFTER_KEY = 1
AFTER_CONFIRM = 2
# The key that ends a turn, as upstream sends it.
END_TURN_KEY = "e"
CONFIRM_KEY = "enter"
# Upstream's template for the Attack button a fight entered from an event opens on, and the box Chaos looks for it in.
# It scores 0.997 on the Global client's button and at most 0.41 on the 711 other captures.
START_ATTACK = "start_attack_event"
START_ATTACK_REGION = (0.394, 0.779, 0.600, 0.858)
# The toast the game puts up when a card costs more than is left. It is the one sure reading of an empty turn: a
# lowered hand spills card art over the readout `board.has_action_points` judges, which then reads as lit.
NO_POINTS = "Not enough AP"
# Where that toast sits, across the middle of the screen. Measured at (0.502, 0.501).
NO_POINTS_REGION = (0.30, 0.42, 0.70, 0.58)
# The game's own check when a turn is ended with a card it would still play, so it is the one reading that knows the
# Action Points: it followed 2 of 18 empty-read turn ends in the logs, exactly the 2 that had cards left to play.
CARDS_LEFT = "can still be used"
CARDS_LEFT_REGION = (0.15, 0.20, 0.85, 0.60)
# The check's Cancel button, which the catalog reads back as Chinese.
CANCEL = "取消"
CANCEL_REGION = (0.15, 0.45, 0.55, 0.80)
# Parked on the task while the hand reads empty under a counter that says it is not: how many times the end of the turn
# has been called back since, or None once the hand reads again.
UNREAD_HAND = "_en_unread_hand"
# Callbacks before the game's check is taken as final, so a hand that never reads cannot stall the turn for good. Each
# one takes about 3s, and a hand has stayed lowered for up to 12s after a play.
CALLBACKS = 4
# Where the hand lays out its cards, by hand size: the left edge of the first and of the last card's name. Medians
# over ~2,600 fully read hands in the September logs, one sighting at 8. Wider hands are taken to span as 7 does.
HAND_SPAN = {2: (0.393, 0.541), 3: (0.328, 0.605), 4: (0.259, 0.675), 5: (0.240, 0.696),
             6: (0.233, 0.711), 7: (0.220, 0.721)}
WIDEST_SPAN = (0.218, 0.730)
# Only keys 1-9 exist, so a tenth card has no key to press.
MAX_KEY = 9
# How many times a card has to stay in hand after its key is pressed before it is left for the rest of the turn.
REFUSALS = 2

_patched = False


class EgoChoice(StandIn):
    """Stands in for the module's `random` while one battle frame runs.

    Only the Ego question is answered here. Every other call - and there are several in that module, for
    picking a card to drag at a Secret Enemy and for the hand-select screens - is handed to the real `random`
    untouched, which is what `StandIn` is for.
    """

    def __init__(self, task, original):
        """Stand in for one frame.

        Args:
            task: The task the frame is running against, whose screen holds the answer.
            original: The module's real `random`, which everything else still goes to.
        """
        super().__init__(original)
        self.task = task

    def choice(self, options):
        """Answer a random choice, narrowing the Ego question to what the EP bar can pay for.

        The defect being fixed is that upstream picks an Ego it cannot afford, not that it picks at random.
        So the choice stays random and only the shortlist changes, which keeps a repeated fight from always
        firing the same Ego.

        Args:
            options: What upstream is choosing between.

        Returns:
            One of the affordable Ego keys when that is the question being asked and the screen gives an
            answer, otherwise whatever the real `random` says.
        """
        if list(options) == list(board.EGO_KEYS):
            ready = board.affordable_egos(self.task)
            if ready:
                firing = self.original.choice(ready)
                logger.info(f"the EP bar covers {', '.join(ready)}, firing {firing}")
                return firing
            # Upstream reads the bar as full and fires anyway, so this is the case worth naming.
            logger.info("the EP bar covers no Ego, so upstream's pick would not have played")
        return self.original.choice(options)


def choose(hand, board, refused):
    """Pick the card to play next, or nothing when the turn is done.

    A turn with points left is planned against the full three, since `board.py` can tell a spent turn from one
    with points but not how many. The game refuses a card there is no room for, so the turn corrects itself
    against the game rather than against a number this module believes in.

    Args:
        hand: Hand cards as `_hand_cards` reads them.
        board: The `cards.Board` to decide against.
        refused: Names the game has already declined to play this turn.

    Returns:
        The hand card to play, or None when nothing is left worth playing.
    """
    playable = [card for card in hand if card.get("key") and card["name"] not in refused]
    chosen = cards.plan(playable, board)
    if chosen:
        return chosen[0]
    # Nothing is worth playing for its own sake, so what is left goes on getting rid of cards that hurt while held.
    # Live, three Bleeds sat out turn after turn with all three points unspent.
    clearing = [card for card in playable
                if cards.worth_clearing(card["name"]) and cards.cost(card["name"]) <= board.action_points]
    return min(clearing, key=lambda card: cards.clearing_order(card["name"]), default=None)


def stretch_card(hand, board, refused, stretched):
    """Find a card whose listed cost is over the turn's budget, worth one try before the turn ends.

    The cost table holds a card's printed cost, and some cards get cheaper during a fight: Mealtime is listed at 6
    and drops by 1 each time Voracity falls, so planned against the turn's three points it was never played at all,
    turn after turn. The game says whether it can be paid for now, so it is asked once a turn.

    Args:
        hand: Hand cards as `_hand_cards` reads them.
        board: The `cards.Board` the turn is planned against.
        refused: Names the game has already declined this turn.
        stretched: Names already tried this way this turn.

    Returns:
        The most valuable such card, or None.
    """
    over = [card for card in hand
            if card.get("key") and card["name"] not in refused and card["name"] not in stretched
            and cards.cost(card["name"]) > board.action_points and cards.worth_playing(card["name"])]
    return max(over, key=lambda card: cards.value(card["name"], board), default=None)


def was_refused(attempted, copies, hand_names):
    """Say whether the card tried last frame is still sitting in hand.

    How many copies are left is what settles it: one fewer than there were means the game took it. Neither the
    size of the hand nor the presence of the card answers it, since a card that draws replaces itself and a
    deck holds several copies of one name.

    Args:
        attempted: The card name tried last frame, or None when nothing was.
        copies: How many of that card were in hand when its key was pressed.
        hand_names: The names now in hand.

    Returns:
        True when the game would not play it, so it should be passed over for the rest of the turn.
    """
    return attempted is not None and hand_names.count(attempted) >= copies


def new_turn(before, after):
    """Say whether the hand has been dealt again since the last frame.

    Args:
        before: The hand size last frame, or None on the first frame of a battle.
        after: The hand size now.

    Returns:
        True when a fresh turn has started, so what the last turn refused no longer applies.
    """
    return before is None or after > before


class Turn:
    """What one turn has learnt: the hand it last saw, the card it tried, and what the game would not play.

    The weakness the enemies show belongs here rather than to the frame. It is a property of the fight, it
    costs a pass over a third of the screen to read, and an attack landing over an enemy hides its badge for
    a frame or two - so it is read once and kept, and a turn that never manages to read one keeps trying.
    """

    def __init__(self, hand_count):
        """Start a turn that has learnt nothing yet.

        Args:
            hand_count: The hand size this turn opened with.
        """
        self.hand_count = hand_count
        self.attempted = None
        self.attempted_copies = 0
        self.refused = set()
        # Cards tried once a turn although their listed cost is over the budget, given up on at the first refusal.
        self.stretched = set()
        # How many frames each card has stayed in hand after its key was pressed, since one can be a frame too soon.
        self.misses = collections.Counter()
        # Keys pressed for a card the counter says is there but OCR never read, each tried once a turn.
        self.blind = set()
        self.weakness = None


def play_key(task, key):
    """Play the card on a key, with upstream's own timings so both paths feel the same to the game.

    Args:
        task: The running task.
        key: The hotkey of the card to play.
    """
    task.send_key(key)
    task.sleep(AFTER_KEY)
    task.send_key(CONFIRM_KEY)
    task.sleep(AFTER_CONFIRM)


def unread_key(hand, count, tried):
    """Find a key the hand counter says holds a card that OCR did not read, and that has not been tried yet.

    Args:
        hand: The hand cards read this frame, keyed by position when the read came up short.
        count: The hand size the hand counter reads.
        tried: Keys already pressed blind this turn.

    Returns:
        The key as a string, or None when every card is accounted for.
    """
    read = {card.get("key") for card in hand}
    return next((str(key) for key in range(1, min(count, MAX_KEY) + 1) if str(key) not in read | tried), None)


def start_attack(task, utils_sortie):
    """Press the Attack button a fight entered from an event opens on.

    Chaos presses it from its own battle handler, but Sortie's never looks. The button hides the end-turn
    button, so upstream's Sortie frame waits for that forever.

    Args:
        task: The running task, whose current frame is searched.
        utils_sortie: Upstream's Sortie module, whose hand count says this is a battle screen at all.

    Returns:
        True when the button was on screen and has been pressed.
    """
    # The hand count is up behind the button, so as in Chaos it keeps the search off every other screen.
    if utils_sortie._read_hand_count(task) is None:
        return False
    button = task.find_one(feature_name=START_ATTACK, box=task.box_of_screen(*START_ATTACK_REGION))
    if not button:
        return False
    task.log_info(f"the fight is waiting on its Attack button, pressing it (match {button.confidence:.2f})")
    task.click_box(button)
    task.sleep(AFTER_KEY)
    return True


def key_at(left_x, count):
    """Say which key plays the card whose name starts at a given point, from where the hand puts each card.

    Upstream gives the leftmost card it read key 1 and counts on from there, which is wrong whenever OCR missed the
    real first card - a lowered hand read as its one raised card, the fourth, and pressed 1 for a minute.

    Args:
        left_x: The left edge of the card's name, as a screen fraction, from `_hand_cards`.
        count: The hand size the hand counter reads.

    Returns:
        The key as a string, or None for a card beyond the ninth.
    """
    if count <= 1:
        return "1"
    first, last = HAND_SPAN.get(count, WIDEST_SPAN)
    slot = min(max(round((left_x - first) / (last - first) * (count - 1)), 0), count - 1)
    return str(slot + 1) if slot < MAX_KEY else None


def out_of_points(task):
    """Say whether the game has just refused a card for want of Action Points.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True while the game's "Not enough AP." toast is up.
    """
    return text_in_region(task, NO_POINTS, NO_POINTS_REGION) is not None


def note_hand_read(task, utils_sortie):
    """Remember whether this frame's hand read came up empty while the counter still showed cards.

    A card the turn cannot afford is drawn lowered, below the band upstream reads names in. So is every card for a
    moment after a play or a deal, and upstream ends the turn on an empty read either way.

    Args:
        task: The running task, which the note is parked on.
        utils_sortie: Upstream's Sortie module, for its hand counter and name reader.
    """
    count = utils_sortie._read_hand_count(task)
    if not count:
        return
    if utils_sortie._hand_card_names(task):
        setattr(task, UNREAD_HAND, None)
    elif getattr(task, UNREAD_HAND, None) is None:
        setattr(task, UNREAD_HAND, 0)


def handle_cards_left(task):
    """Cancel the end of a turn upstream called on an unread hand, once the game says a card can still be played.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when the end was called back. False leaves the check to upstream's centre Confirm, which is how an end
        the picker chose on purpose still goes through.
    """
    callbacks = getattr(task, UNREAD_HAND, None)
    if callbacks is None or callbacks >= CALLBACKS or not text_in_region(task, CARDS_LEFT, CARDS_LEFT_REGION):
        return False
    cancel = text_in_region(task, CANCEL, CANCEL_REGION)
    if not cancel:
        return False
    task.log_info("the game says cards can still be played, so the hand was not raised yet - cancelling the end of turn")
    setattr(task, UNREAD_HAND, callbacks + 1)
    task.click_box(cancel)
    task.sleep(AFTER_KEY)
    return True


def turn_of(task, hand_count):
    """Bring the per-turn bookkeeping up to date and hand it back.

    Args:
        task: The running task, which the state is parked on.
        hand_count: The hand size read this frame.

    Returns:
        The `Turn` in progress, fresh when the hand has just been dealt again.
    """
    turn = getattr(task, TURN, None)
    if turn is None or new_turn(turn.hand_count, hand_count):
        turn = Turn(hand_count)
        setattr(task, TURN, turn)
    turn.hand_count = hand_count
    return turn


def install():
    """Put the card picker in place of upstream's press-every-key fallback.

    `handle_battle_page` reaches `_try_all_card_keys` as a module global, which Python resolves when the call
    is made, so rebinding it on the module is enough. That leaves every other line of upstream's battle frame
    running exactly as it did. It has two callers, and rebinding takes over both - the other is the escape
    hatch upstream reaches for after a card the list *did* name has failed to play three times running, which
    is usually one there are no Action Points for, so choosing a different card beats flailing at every key.

    Runs once per task load, so it has to be safe to call again: a replacement already in place is left alone
    rather than wrapped in a second one.
    """
    utils = loaded("utils")
    utils_sortie = loaded("utils_sortie")
    if utils is None or utils_sortie is None:
        return
    if getattr(utils_sortie._try_all_card_keys, "_en_picker", False):
        return
    blind_fallback = utils_sortie._try_all_card_keys
    read_names = utils_sortie._hand_card_names
    read_hand = utils_sortie._hand_cards

    def _hand_cards(task):
        """Read the hand, keying it by where each card sits whenever OCR read fewer or more cards than the counter.

        Upstream counts keys on from the leftmost card it read, so a missed card shifts every key after it. Done
        here rather than in the picker, because upstream's Play Priority list and the battle recorder read keys
        from this too.

        Args:
            task: The running task.

        Returns:
            The hand cards as upstream reads them, with their keys corrected when the read came up short.
        """
        hand = read_hand(task)
        count = utils_sortie._read_hand_count(task)
        if count and any(str(card.get("key") or "").isdigit() and int(card["key"]) > count for card in hand):
            # A key past the hand size cannot exist, so text that is not a card got into the read. Live, a Bleed tooltip
            # was read as "Damage on" and "Combatants" in a hand of 4, pushing the real Bleed to key 9. The data names
            # every real card, so only what it knows is kept and keyed by position below.
            hand = [card for card in hand if cards.canonical(card["name"]) in cards.CARD_COST]
        if hand and count and len(hand) != count:
            hand = [{**card, "key": key_at(card["left_x"], count)} for card in hand]
            task.log_info(f"read {len(hand)} of {count} cards, so keys come from where each sits: "
                          f"{[(card['name'], card['key']) for card in hand]}")
        return hand

    def _hand_card_names(task):
        """Read the hand's card names once per OCR pass rather than once per caller.

        Upstream calls this twice a frame - directly, and again inside `_hand_cards` - and the picker would
        have made it three. Each call walks `all_texts` and logs a line for every box on screen, which on a
        battle screen is the noisiest thing the bot does.

        Args:
            task: The running task.

        Returns:
            The name boxes, from this frame's reading or the one already taken from the same OCR pass.
        """
        read_for, names = getattr(task, HAND_CACHE, (None, None))
        if read_for is task.all_texts:
            return names
        # Upstream prints one line per box on screen here, plus two summaries - about 26,700 lines of a
        # 244,000-line day. It is a debugging aid for its own region filter, shipped at info level, so it is
        # dropped to debug rather than removed: `python main_debug.py` still shows it when the filter misreads.
        with standing_in(task, log_info=logger.debug):
            names = read_names(task)
        setattr(task, HAND_CACHE, (task.all_texts, names))
        return names

    def _try_all_card_keys(task, count):
        """Play the best card in hand, in place of pressing every key in turn.

        Args:
            task: The running task.
            count: The hand size upstream read off the hand counter, which holds steady while OCR drops cards.
        """
        if not utils._get_config_value(task, SMART_CARD_PLAY, True):
            blind_fallback(task, count)
            return

        # Canonical, because OCR spells a name differently from frame to frame and a refusal has to match the
        # card it was about across them.
        hand = [{**card, "name": cards.canonical(card["name"])} for card in utils_sortie._hand_cards(task) or []]
        names = [card["name"] for card in hand]
        turn = turn_of(task, count)

        if was_refused(turn.attempted, turn.attempted_copies, names):
            turn.misses[turn.attempted] += 1
            # Live, Magnetic Field stayed in hand once with all three points to spend, and was given up on for the turn.
            # A card tried over its listed cost is given up on at once: the game declining it is the expected answer.
            if turn.misses[turn.attempted] >= REFUSALS or turn.attempted in turn.stretched:
                turn.refused.add(turn.attempted)
                task.log_info(f"the game would not play {turn.attempted}, leaving it for the rest of this turn")

        # The readout says whether anything is left to spend, not how much, so a turn with points left is
        # planned against a full three and corrected by what the game will actually accept.
        points = cards.BASE_ACTION_POINTS if board.has_action_points(task) and not out_of_points(task) else 0
        if turn.weakness is None:
            # Read once a turn, so this is also the one frame a turn to say what it opened holding.
            turn.weakness = board.weakness(task)
            against = f"enemies weak to {turn.weakness}" if turn.weakness else "no shared enemy weakness"
            budget = "Action Points to spend" if points else "no Action Points"
            task.log_info(f"turn opens with {budget}, {against}, hand {names}")
        state = cards.Board(action_points=points, weakness=turn.weakness)
        card = choose(hand, state, turn.refused)
        if card is None:
            if not names:
                # Upstream ends an empty hand itself, so there is nothing here to do and nothing to say.
                return
            turn.attempted = None
            # A card OCR missed is still in hand. Live, an unread Cobalt Light was left behind with points to spend,
            # so each missing key is tried once before giving up on the turn.
            blind = unread_key(hand, count, turn.blind) if points else None
            if blind:
                task.log_info(f"read {len(names)} of {count} cards and none worth playing, trying unread key {blind}")
                turn.blind.add(blind)
                play_key(task, blind)
                return
            stretch = stretch_card(hand, state, turn.refused, turn.stretched) if points else None
            if stretch:
                name = stretch["name"]
                task.log_info(f"trying {name} on key {stretch['key']} although it is listed at {cards.cost(name)} AP,"
                              f" since its cost can fall during a fight")
                turn.stretched.add(name)
                turn.attempted = name
                turn.attempted_copies = names.count(name)
                play_key(task, stretch["key"])
                return
            spent = "" if points else ", no Action Points left"
            task.log_info(f"nothing left worth playing in {names}{spent}, ending the turn")
            task.send_key(END_TURN_KEY)
            task.sleep(AFTER_KEY)
            return

        name = card["name"]
        task.log_info(f"playing {name} for {cards.cost(name)} AP on key {card['key']}, "
                      f"worth {cards.value(name, state):.0f}")
        turn.attempted = name
        turn.attempted_copies = names.count(name)
        play_key(task, card["key"])

    original_page = utils_sortie.handle_battle_page

    def handle_battle_page(task):
        """Start a fight still waiting on its Attack button, otherwise run upstream's battle frame with the Ego choice answered from the screen.

        Args:
            task: The running task.

        Returns:
            True when the Attack button was pressed, otherwise whatever upstream's own handler returns.
        """
        if start_attack(task, utils_sortie):
            return True
        note_hand_read(task, utils_sortie)
        was = utils_sortie.random
        utils_sortie.random = EgoChoice(task, was)
        try:
            return original_page(task)
        finally:
            utils_sortie.random = was

    replace("handle_battle_page", handle_battle_page)
    insert_before("handle_center_confirm", handle_cards_left)

    # Marked so a later task load recognises the replacement and does not wrap it in itself.
    _try_all_card_keys._en_picker = True
    utils_sortie._try_all_card_keys = _try_all_card_keys
    utils_sortie._hand_card_names = _hand_card_names
    utils_sortie._hand_cards = _hand_cards
    # Upstream's own card-name filter excludes the type label printed under each card, but it lists only the
    # Chinese labels. On the Global client they are drawn in English, so every one of them passed straight
    # through and was read as a card in hand. Wrapped rather than replaced: the catalog rewrites some English
    # labels back into Chinese, and upstream's list is what catches those.
    reads_as_card = utils_sortie._is_card_name

    def _is_card_name(name):
        """Say whether a reading off the hand names a card, in either language.

        Args:
            name: The text the reader returned for one hand card.

        Returns:
            True when both upstream's filter and this fork's agree it is a card.
        """
        return bool(reads_as_card(name)) and cards.is_card_name(name)

    utils_sortie._is_card_name = _is_card_name
    logger.info("sortie battles now pick a card instead of pressing every key")


def apply():
    """Have the card picker stand in for upstream's fallback, once the modes have been imported."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
