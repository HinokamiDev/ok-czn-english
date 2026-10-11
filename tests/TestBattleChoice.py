"""Check the pick made on a card offer opened mid-fight, such as Nia's Curiosity's three cards from the Draw Pile."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en.battle import TURN  # noqa: E402
from src.en.battle_choice import (  # noqa: E402
    LAST_OFFER, best_of, handle_battle_card_choice, intent_of, offer_of, worst_of,
)
from tests.fakes import FakeBox  # noqa: E402

# The offer the stuck fallback answered at random in the live run, at the positions it was read.
LIVE_OFFER = [{"name": "Bottomless Hunger", "x": 0.2062, "y": 0.3269},
              {"name": "Adagio", "x": 0.4578, "y": 0.3269},
              {"name": "Nia's Curiosity", "x": 0.7089, "y": 0.3269}]


class FakeTask:
    height = 1080

    def __init__(self, in_fight=True, prompt="Select 1 card to draw"):
        # One line above the cards, and one inside them that says the opposite, which must not count.
        self.all_texts = [FakeBox(prompt, 0.5, 0.1), FakeBox("Discard 1", 0.45, 0.6)]
        if in_fight:
            setattr(self, TURN, object())
        self.logged = []

    def log_info(self, message):
        self.logged.append(message)

    def sleep(self, seconds):
        pass


def fake_utils(found):
    clicks = []
    module = types.SimpleNamespace(recognize_cards=lambda task, page="": [dict(card) for card in found],
                                   _move_and_click=lambda task, x, y: clicks.append((x, y)))
    return module, clicks


class TestBattleChoice(unittest.TestCase):
    def test_the_offer_is_taken_once_it_has_held_for_a_frame(self):
        task = FakeTask()
        utils, clicks = fake_utils(LIVE_OFFER)
        self.assertTrue(handle_battle_card_choice(task, utils))
        self.assertEqual(clicks, [])
        self.assertTrue(handle_battle_card_choice(task, utils))
        self.assertEqual(len(clicks), 1)
        self.assertIsNone(getattr(task, LAST_OFFER))

    def test_the_pick_is_the_best_valued_card_not_a_random_one(self):
        pick = best_of(offer_of(LIVE_OFFER))
        self.assertIn(pick["name"], {card["name"] for card in LIVE_OFFER})
        self.assertEqual(best_of(offer_of(LIVE_OFFER)), pick)

    def test_cards_in_the_hand_band_are_not_an_offer(self):
        hand = [{"name": "Strike", "x": 0.3, "y": 0.85}, {"name": "Strike", "x": 0.4, "y": 0.85}]
        self.assertEqual(offer_of(hand), [])
        task = FakeTask()
        utils, clicks = fake_utils(hand)
        self.assertFalse(handle_battle_card_choice(task, utils))

    def test_nothing_happens_outside_a_fight(self):
        task = FakeTask(in_fight=False)
        utils, clicks = fake_utils(LIVE_OFFER)
        self.assertFalse(handle_battle_card_choice(task, utils))
        self.assertFalse(handle_battle_card_choice(task, utils))
        self.assertEqual(clicks, [])


class TestIntent(unittest.TestCase):
    def test_a_draw_prompt_keeps_the_best_card(self):
        task = FakeTask(prompt="Select a card to add to your hand")
        utils, clicks = fake_utils(LIVE_OFFER)
        handle_battle_card_choice(task, utils)
        handle_battle_card_choice(task, utils)
        best = best_of(offer_of(LIVE_OFFER))
        self.assertEqual(clicks, [(best["x"], best["y"])])

    def test_a_discard_prompt_throws_away_the_weakest(self):
        task = FakeTask(prompt="Select 1 card to Discard")
        utils, clicks = fake_utils(LIVE_OFFER)
        handle_battle_card_choice(task, utils)
        handle_battle_card_choice(task, utils)
        worst = worst_of(offer_of(LIVE_OFFER))
        self.assertEqual(clicks, [(worst["x"], worst["y"])])

    def test_an_unclear_prompt_is_left_alone_and_logged(self):
        task = FakeTask(prompt="Draw one, discard the rest")
        utils, clicks = fake_utils(LIVE_OFFER)
        handle_battle_card_choice(task, utils)
        self.assertFalse(handle_battle_card_choice(task, utils))
        self.assertEqual(clicks, [])
        self.assertTrue(any("neither keep nor discard" in line for line in task.logged))

    def test_names_read_differently_each_frame_still_settle(self):
        task = FakeTask(prompt="Select an attribute.")
        offers = [[{"name": name, "x": x, "y": 0.33} for name, x in zip(names, (0.245, 0.508, 0.757))]
                  for names in (("Archetype:", "Archetype: ∆", "Archetype:"), ("Archetype:", "Archetype:", "Archetype: ["))]
        clicks = []
        for offer in offers:
            utils, found = fake_utils(offer)
            handle_battle_card_choice(task, utils)
            clicks += found
        self.assertEqual(len(clicks), 1)

    def test_intent_reading(self):
        self.assertEqual(intent_of("select a card to draw"), "keep")
        self.assertEqual(intent_of("choose a card to discard"), "discard")
        self.assertEqual(intent_of("select an attribute."), "keep")
        self.assertEqual(intent_of("select 1 card to discard"), "discard")
        self.assertIsNone(intent_of("tap and hold the card"))


if __name__ == "__main__":
    unittest.main()
