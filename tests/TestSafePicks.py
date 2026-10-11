"""Check that card picks the user has an opinion on are never guessed.

The Epiphany tests drive upstream's own `handle_view_original` through the wrapper, with the screen readers
stubbed, so the seams the wrapper relies on are exercised rather than assumed. The deck tests use a stand-in for
`select_card` that reads its cards through the same module attribute upstream does.
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402

from src.en import ask, notify, status  # noqa: E402
from src.en import safe_picks  # noqa: E402
from src.en.safe_picks import (  # noqa: E402
    ASK_ALWAYS, ASK_LISTED, ASK_TIMEOUT, ASKING, CLICKED_AT, COPY_ONLY_PRIORITISED, DEFAULTS, MAX_COPIES,
    NEVER_REMOVE, PAUSE_ALWAYS, RANDOM, SETTLE_SECONDS, STRICT_MATCHING, UNMATCHED_EPIPHANY, UNREADABLE_SLOT_EMPTY,
    copies_made, guarding_copy_choice, guarding_deck, guarding_epiphany, install, page_name, quiet_while_asking,
    reading_unknown_as_empty, seed, words_match,
)
from tests.fakes import FakeBox  # noqa: E402

BERYL_RETAIN = {"name": "Opening Found", "description": "Retain. On Retain, 1 Extra Attack.", "x": 0.3, "y": 0.5}
BERYL_DRAW = {"name": "Opening Found", "description": "Draw 1. Retaliate in turn. Extra damage. Attack.", "x": 0.5, "y": 0.5}
BERYL_COST = {"name": "Opening Found", "description": "Cost -1. 150% Damage.", "x": 0.7, "y": 0.5}


class FakeTask:
    """A running mode, holding its settings and counting pauses."""

    name = "自动卡厄思模式"

    def __init__(self, **settings):
        self.config = {"闪光优先级": [], "闪光卡牌列表": [], "复制卡牌列表": [], **settings}
        self.default_config = {}
        self.member_status = {"deck": {}}
        self.logged = []
        self.paused = 0

    def log_info(self, message):
        self.logged.append(message)

    def pause(self):
        self.paused += 1


class EpiphanyScreen:
    """Stub upstream's screen readers for one Epiphany offer, and record what gets clicked."""

    def __init__(self, cards, target=False):
        self.cards = cards
        self.target = target
        self.clicks = []

    def __enter__(self):
        box = FakeBox("查看原件", 0.890, 0.051)
        target = ([object()], [(0.11, 0.22)]) if self.target else ([], [])
        self.patches = [
            patch.object(utils, "find_box_at_point", lambda task, x, y: box if (x, y) == (0.890, 0.051) else None),
            patch.object(utils, "_get_game_text", lambda task, key: key),
            patch.object(utils, "recognize_cards", lambda task, page="": [dict(card) for card in self.cards]),
            patch.object(utils, "find_target_card", lambda task: target),
            patch.object(utils, "_matching_meditation_card_names", lambda task, cards: []),
            patch.object(utils, "_move_and_click", lambda task, x, y: self.clicks.append((x, y))),
            patch.object(notify, "announce", lambda task, message, kind=None: task.log_info(message)),
        ]
        for each in self.patches:
            each.start()
        return self

    def __exit__(self, *exc):
        for each in reversed(self.patches):
            each.stop()


def handler():
    """Wrap upstream's Epiphany handler the way `install` does."""
    return guarding_epiphany(utils.handle_view_original, utils)


class TestWordsMatch(unittest.TestCase):
    def test_words_have_to_appear_whole(self):
        self.assertTrue(words_match("Opening Found Retain Extra Attack", "Opening Found：:Retain. On Retain, 1 Extra Attack."))
        self.assertFalse(words_match("Opening Found Retain Extra Attack", "Opening Found：:Retain. 1 Extra hit."))

    def test_word_order_does_not_matter_since_ocr_scrambles_lines(self):
        # Read off the live client: the same offer, two frames apart.
        scrambled = ("Flame Dragon's Jewel：:[Unique / Initiation]Increase CriticalChance of this unit by30%"
                     "Tenacity Damage, 1On Critical Hit, 1Ember")
        self.assertTrue(words_match("Flame Dragon's Jewel Critical Hit Ember", scrambled))

    def test_scattered_letters_are_not_enough(self):
        text = "Opening Found：:" + BERYL_DRAW["description"]
        # Upstream's subsequence test accepts this: every letter appears somewhere, in order.
        self.assertTrue(utils.is_subsequence("OpeningFoundRetainExtraAttack", text))
        self.assertFalse(words_match("Opening Found Retain Extra Attack", text))

    def test_spacing_and_case_from_ocr_do_not_matter(self):
        self.assertTrue(words_match("source of water wave", "Sourceof Water：:Heal. Gain 1 AP. WAVE"))

    def test_empty_entry_matches_nothing(self):
        self.assertFalse(words_match("  ", "anything"))


class TestEpiphany(unittest.TestCase):
    def test_priority_beats_the_target_marker(self):
        task = FakeTask(**{"闪光优先级": ["Opening Found Retain Extra Attack"]})
        with EpiphanyScreen([BERYL_DRAW, BERYL_RETAIN, BERYL_COST], target=True) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual(screen.clicks, [(BERYL_RETAIN["x"], BERYL_RETAIN["y"])])

    def test_target_marker_still_used_when_nothing_matches(self):
        task = FakeTask()
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST], target=True) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual(screen.clicks, [(0.11, 0.22)])
        self.assertEqual(task.paused, 0)

    def test_loose_match_on_the_wrong_variant_is_not_taken(self):
        # Only the draw variant is offered. Upstream's subsequence test would take it for the Retain one.
        task = FakeTask(**{"闪光优先级": ["Opening Found Retain Extra Attack"]})
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST]) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual(screen.clicks, [])
        self.assertEqual(task.paused, 1)

    def test_listed_card_without_a_match_pauses_instead_of_guessing(self):
        task = FakeTask(**{"闪光卡牌列表": ["Opening Found"]})
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST]) as screen, patch.object(utils.random, "choice") as choice:
            self.assertTrue(handler()(task))
        choice.assert_not_called()
        self.assertEqual(screen.clicks, [])
        self.assertEqual(task.paused, 1)
        self.assertTrue(any("Paused" in line for line in task.logged))

    def test_unlisted_card_keeps_upstreams_random_pick(self):
        task = FakeTask(**{"闪光卡牌列表": ["Source of Water"]})
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST]) as screen, \
                patch.object(utils.random, "choice", side_effect=lambda cards: cards[-1]):
            self.assertTrue(handler()(task))
        self.assertEqual(screen.clicks, [(BERYL_COST["x"], BERYL_COST["y"])])
        self.assertEqual(task.paused, 0)

    def test_always_pause(self):
        task = FakeTask(**{UNMATCHED_EPIPHANY: PAUSE_ALWAYS})
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST]) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual((screen.clicks, task.paused), ([], 1))

    def test_random_restores_upstream(self):
        task = FakeTask(**{"闪光卡牌列表": ["Opening Found"], UNMATCHED_EPIPHANY: RANDOM})
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST]) as screen, \
                patch.object(utils.random, "choice", side_effect=lambda cards: cards[0]):
            self.assertTrue(handler()(task))
        self.assertEqual((screen.clicks, task.paused), ([(BERYL_DRAW["x"], BERYL_DRAW["y"])], 0))

    def test_loose_matching_can_be_switched_back(self):
        task = FakeTask(**{"闪光优先级": ["Opening Found Retain Extra Attack"], STRICT_MATCHING: False})
        with EpiphanyScreen([BERYL_DRAW, BERYL_COST]) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual(screen.clicks, [(BERYL_DRAW["x"], BERYL_DRAW["y"])])

    def test_other_screens_pass_straight_through(self):
        task = FakeTask()
        with EpiphanyScreen([BERYL_DRAW]) as screen, patch.object(utils, "find_box_at_point", lambda *a: None):
            self.assertFalse(handler()(task))
        self.assertEqual(screen.clicks, [])


JEWEL_TENACITY = {"name": "Flame Dragon's Jewel", "x": 0.2057, "y": 0.3269,
                  "description": "Increase Damage[Unique /Initiation]Amount of Attack Cardsof this unit by 20%When an Attack Card isactivated, 1 TenacityDamage to the target"}
JEWEL_CRIT = {"name": "Flame D'sJewel", "x": 0.4578, "y": 0.3278,
              "description": "[Unique / Initiation]Increase CriticalChance of this unit by30%On Critical Hit, 1Tenacity Damage, 1Ember"}
JEWEL_PASSION = {"name": "Flame Dragon's Jewel", "x": 0.7104, "y": 0.3269,
                 "description": "[Unique /InitiationIncrease DamageAmount of Attack CardsWhen an Attack Card isof this unit by 30%Weakness to the targetactivated, 1 Passion"}


class TestLiveReadings(unittest.TestCase):
    """Replays the Flame Dragon's Jewel offer exactly as the first live run read it."""

    def test_garbled_name_is_read_under_the_screens_name(self):
        self.assertEqual(page_name([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]), "Flame Dragon's Jewel")
        task = FakeTask(**{"闪光优先级": ["Flame Dragon's Jewel Critical Hit Ember"]})
        with EpiphanyScreen([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual(screen.clicks, [(JEWEL_CRIT["x"], JEWEL_CRIT["y"])])

    def test_screen_is_left_alone_while_the_pick_animates_out(self):
        task = FakeTask(**{"闪光卡牌列表": ["Flame Dragon's Jewel"]})
        setattr(task, CLICKED_AT, safe_picks.time.monotonic())
        with EpiphanyScreen([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]) as screen:
            self.assertTrue(handler()(task))
        self.assertEqual((screen.clicks, task.paused), ([], 0))

    def test_a_pick_starts_the_settle_window(self):
        task = FakeTask(**{"闪光优先级": ["Flame Dragon's Jewel 30% Passion"]})
        wrapped = handler()
        with EpiphanyScreen([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]) as screen:
            wrapped(task)
            wrapped(task)
        self.assertEqual(screen.clicks, [(JEWEL_PASSION["x"], JEWEL_PASSION["y"])])
        later = safe_picks.time.monotonic() + SETTLE_SECONDS + 1
        with patch.object(safe_picks.time, "monotonic", return_value=later), \
                EpiphanyScreen([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]) as screen:
            wrapped(task)
        self.assertEqual(len(screen.clicks), 1)


class TestAsking(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = patch.object(status, "PATH", Path(self.folder.name) / "son-calisma.json")
        self.path.start()

    def tearDown(self):
        self.path.stop()
        self.folder.cleanup()

    def read_request(self):
        return json.loads(ask.request_path().read_text(encoding="utf-8"))

    def answer(self, request_id, choice):
        ask.answer_path().write_text(json.dumps({"id": request_id, "secim": choice}), encoding="utf-8")

    def test_question_is_published_then_the_answer_clicked(self):
        task = FakeTask(**{"闪光卡牌列表": ["Flame Dragon's Jewel"], UNMATCHED_EPIPHANY: ASK_LISTED})
        wrapped = handler()
        offers = [JEWEL_PASSION, JEWEL_TENACITY, JEWEL_CRIT]
        with EpiphanyScreen(offers) as screen:
            self.assertTrue(wrapped(task))
            request = self.read_request()
            self.assertEqual([option["metin"].split(":")[0] for option in request["secenekler"]],
                             ["left", "middle", "right"])
            self.assertEqual(status.read()["durum"], "karar_bekliyor")
            self.assertTrue(wrapped(task))
            self.assertEqual(screen.clicks, [])
            self.answer(request["id"], 2)
            self.assertTrue(wrapped(task))
        self.assertEqual(screen.clicks, [(JEWEL_CRIT["x"], JEWEL_CRIT["y"])])
        self.assertFalse(ask.request_path().exists())
        self.assertEqual(status.read()["durum"], "calisiyor")
        self.assertEqual(task.paused, 0)

    def test_answer_for_another_request_is_ignored(self):
        task = FakeTask(**{UNMATCHED_EPIPHANY: ASK_ALWAYS})
        wrapped = handler()
        with EpiphanyScreen([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]) as screen:
            wrapped(task)
            self.answer("someone-else", 1)
            wrapped(task)
        self.assertEqual(screen.clicks, [])

    def test_no_answer_in_time_pauses(self):
        task = FakeTask(**{UNMATCHED_EPIPHANY: ASK_ALWAYS, ASK_TIMEOUT: 0})
        wrapped = handler()
        with EpiphanyScreen([JEWEL_TENACITY, JEWEL_CRIT, JEWEL_PASSION]) as screen:
            wrapped(task)
            safe_picks.time.sleep(0.01)
            wrapped(task)
        self.assertEqual((screen.clicks, task.paused), ([], 1))
        self.assertIsNone(getattr(task, ASKING))

    def test_stuck_fallback_stays_away_while_asking(self):
        task = FakeTask()
        fallback = []
        guarded = quiet_while_asking(lambda task_: fallback.append(1) or True)
        setattr(task, ASKING, {"id": "x"})
        self.assertFalse(guarded(task))
        setattr(task, ASKING, None)
        self.assertTrue(guarded(task))
        self.assertEqual(fallback, [1])


class TestUnreadableSlots(unittest.TestCase):
    def run_reading(self, rgb, enabled=True):
        task = FakeTask(**{UNREADABLE_SLOT_EMPTY: enabled})
        seen = []

        def quality_of(task_, point, allow_empty=False):
            return "传说", rgb

        def handler_(task_):
            seen.append(utils._equipment_quality_at(task_, (0.5, 0.5), allow_empty=True))

        with patch.object(utils, "_equipment_quality_at", quality_of):
            reading_unknown_as_empty(handler_, utils)(task)
        return seen[0][0]

    def test_grey_read_on_the_live_client_counts_as_empty(self):
        for rgb in ((56, 56, 55), (60, 59, 58), (78, 67, 50), (101, 80, 57)):
            with self.subTest(rgb=rgb):
                self.assertEqual(self.run_reading(rgb), "")

    def test_mythic_violet_stays_the_top_tier(self):
        self.assertEqual(self.run_reading((137, 82, 164)), "传说")

    def test_can_be_switched_back(self):
        self.assertEqual(self.run_reading((56, 56, 55), enabled=False), "传说")


def deck_card(name, description="", y=0.5, selected=False):
    return {"name": name, "description": description, "x": 0.4, "y": y, "selected": selected, "type": "基础技能"}


class FakeSelectCard:
    """Picks the way `select_card` does: the priority names first, then the bottom card, reading through `utils`."""

    def __init__(self):
        self.calls = 0

    def __call__(self, task, card_names, count=1, action=""):
        self.calls += 1
        cards = utils.recognize_cards_in_deck(task, page=f"select_card-{action}")
        for target in card_names:
            for card in cards:
                if target in card["name"] and not card["selected"]:
                    card["selected"] = True
                    return True
        if cards:
            max(cards, key=lambda card: card["y"])["selected"] = True
            return True
        task.logged.append("skip")
        return True


class TestDeck(unittest.TestCase):
    def run_select(self, task, cards, action, names):
        shown = [dict(card) for card in cards]
        with patch.object(utils, "recognize_cards_in_deck", lambda task, page="": shown):
            guarding_deck(FakeSelectCard(), utils)(task, names, count=1, action=action)
        return shown

    def test_copy_waits_for_the_prioritised_variant(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], "闪光优先级": ["Opening Found Retain Extra Attack"]})
        shown = self.run_select(task, [deck_card("Opening Found", "Cost -1. 150% Damage.", y=0.2)], "复制", ["Opening Found"])
        self.assertFalse(shown[0]["selected"])
        self.assertIn("skip", task.logged)
        self.assertEqual(copies_made(task), {})

    def test_copy_takes_the_prioritised_variant_and_counts_it(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], "闪光优先级": ["Opening Found Retain Extra Attack"]})
        shown = self.run_select(task, [deck_card("Opening Found", BERYL_RETAIN["description"])], "复制", ["Opening Found"])
        self.assertTrue(shown[0]["selected"])
        self.assertEqual(copies_made(task), {"openingfound": 1})

    def test_copy_stops_at_the_limit(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], MAX_COPIES: 3})
        for _ in range(4):
            self.run_select(task, [deck_card("Opening Found", "x")], "复制", ["Opening Found"])
        # The original plus two copies makes three.
        self.assertEqual(copies_made(task), {"openingfound": 2})

    def test_copies_already_on_screen_count_towards_the_limit(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], MAX_COPIES: 2})
        shown = self.run_select(task, [deck_card("Opening Found", "x"), deck_card("Opening Found", "x", y=0.3)],
                                "复制", ["Opening Found"])
        self.assertFalse(any(card["selected"] for card in shown))

    def test_variant_check_can_be_switched_off(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], "闪光优先级": ["Opening Found Retain"],
                           COPY_ONLY_PRIORITISED: False})
        shown = self.run_select(task, [deck_card("Opening Found", "Cost -1.")], "复制", ["Opening Found"])
        self.assertTrue(shown[0]["selected"])

    def test_never_remove_spares_a_basic_heal(self):
        task = FakeTask(**{NEVER_REMOVE: ["Heal"]})
        cards = [deck_card("Mika Basic Heal", "Heal 100%.", y=0.9), deck_card("Mika Basic Attack", "100% Damage.", y=0.2)]
        shown = self.run_select(task, cards, "移除", [])
        self.assertEqual([card["selected"] for card in shown], [False, True])

    def test_other_actions_are_untouched(self):
        task = FakeTask(**{NEVER_REMOVE: ["Heal"]})
        shown = self.run_select(task, [deck_card("Heal Card", "Heal 100%.")], "闪光", [])
        self.assertTrue(shown[0]["selected"])


class TestCopyChoice(unittest.TestCase):
    def run_choice(self, task, cards, target=False):
        clicks = []
        box = FakeBox("请选择要复制的卡牌", 0.498, 0.133)
        target_answer = ([object()], [(0.9, 0.9)]) if target else ([], [])
        with patch.object(utils, "find_box_at_point", lambda task, x, y: box), \
                patch.object(utils, "_get_game_text", lambda task, key: key), \
                patch.object(utils, "recognize_cards", lambda task, page="": [dict(card) for card in cards]), \
                patch.object(utils, "find_target_card", lambda task: target_answer), \
                patch.object(utils, "_move_and_click", lambda task, x, y: clicks.append((x, y))), \
                patch.object(utils.TriggerTask, "sleep", lambda *a: None, create=True):
            task.sleep = lambda seconds: None
            result = guarding_copy_choice(utils.handle_copy_card_choice, utils)(task)
        return result, clicks

    def test_listed_match_beats_the_target_marker_and_counts(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"]})
        result, clicks = self.run_choice(task, [BERYL_COST, BERYL_RETAIN], target=True)
        self.assertTrue(result)
        self.assertEqual(clicks, [(BERYL_COST["x"], BERYL_COST["y"])])
        self.assertEqual(copies_made(task), {"openingfound": 1})

    def test_wrong_variant_is_not_copied(self):
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], "闪光优先级": ["Opening Found Retain Extra Attack"]})
        result, clicks = self.run_choice(task, [BERYL_COST, BERYL_RETAIN])
        self.assertEqual(clicks, [(BERYL_RETAIN["x"], BERYL_RETAIN["y"])])
        task = FakeTask(**{"复制卡牌列表": ["Opening Found"], "闪光优先级": ["Opening Found Retain Extra Attack"]})
        result, clicks = self.run_choice(task, [BERYL_COST])
        self.assertFalse(result)
        self.assertEqual(clicks, [])


class TestSettings(unittest.TestCase):
    def test_seeded_on_modes_that_choose_cards(self):
        task = types.SimpleNamespace(default_config={"复制卡牌列表": []}, config_description={}, config_type={})
        seed(task)
        self.assertEqual({key: task.default_config[key] for key in DEFAULTS}, DEFAULTS)
        self.assertIn(UNMATCHED_EPIPHANY, task.config_type)
        self.assertEqual(set(DEFAULTS), set(task.config_description))

    def test_not_seeded_elsewhere(self):
        task = types.SimpleNamespace(default_config={}, config_description={}, config_type={})
        seed(task)
        self.assertEqual(task.default_config, {})

    def test_install_wraps_each_picker_once(self):
        module = types.ModuleType("fake_utils")
        for name in ("handle_view_original", "select_card", "handle_copy_card_choice", "handle_stuck_log",
                     "handle_equipment"):
            setattr(module, name, (lambda name: lambda *a, **k: name)(name))
        install(module)
        first = module.select_card
        install(module)
        self.assertIs(module.select_card, first)
        self.assertEqual(module.select_card.__name__, "<lambda>")
        self.assertIn(safe_picks.DECK_TAG, module.select_card._en_wraps)


if __name__ == "__main__":
    unittest.main()
