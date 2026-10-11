"""Check that a card listed over the turn's budget still gets one try, since its cost can fall mid-fight.

Mealtime is listed at 6 Action Points and drops by 1 each time Voracity falls. Planned against the turn's three,
it sat in hand for every turn of the live run while the turn was ended with points left.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import cards  # noqa: E402
from src.en.battle import choose, stretch_card  # noqa: E402

# The hand the live run ended its turn on: "nothing left worth playing in ['Mealtime', 'Homing Laser', 'Homing Laser']".
LIVE_HAND = [{"name": "Mealtime", "key": "1"}, {"name": "Homing Laser", "key": "2"}, {"name": "Homing Laser", "key": "3"}]


class TestStretchCost(unittest.TestCase):
    def test_mealtime_is_listed_over_a_turns_budget(self):
        self.assertGreater(cards.cost("Mealtime"), cards.BASE_ACTION_POINTS)

    def test_planning_alone_never_picks_it(self):
        self.assertIsNone(choose(LIVE_HAND, cards.Board(), refused={"Homing Laser"}))

    def test_it_gets_one_try_before_the_turn_ends(self):
        card = stretch_card(LIVE_HAND, cards.Board(), refused={"Homing Laser"}, stretched=set())
        self.assertEqual(card["name"], "Mealtime")

    def test_only_once_a_turn(self):
        self.assertIsNone(stretch_card(LIVE_HAND, cards.Board(), refused={"Homing Laser"}, stretched={"Mealtime"}))

    def test_a_refused_card_is_not_tried_again(self):
        self.assertIsNone(stretch_card(LIVE_HAND, cards.Board(), refused={"Homing Laser", "Mealtime"}, stretched=set()))


if __name__ == "__main__":
    unittest.main()
