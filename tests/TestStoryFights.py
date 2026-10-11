"""Check when the Story mode takes a fight over with the Sortie card player, and when it hands it back."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import story_fights  # noqa: E402
from src.en.story_fights import FIGHT_OVER_SECONDS, IDLE_SECONDS, STATE, handle_story_fight_without_auto  # noqa: E402


class FakeTask:
    def __init__(self):
        self.logged = []
        self.finish_turn = True

    def log_info(self, message):
        self.logged.append(message)

    def box_of_screen(self, *region):
        return region

    def find_feature(self, feature_name=None, box=None):
        return [object()] if self.finish_turn else []


class Fight:
    """A Sortie module whose hand counter and card names the test sets."""

    def __init__(self):
        self.count, self.names = 5, ["Strike", "Homing Laser"]
        self.module = types.SimpleNamespace(_read_hand_count=lambda task: self.count,
                                            _hand_card_names=lambda task: list(self.names or []))


class TestStoryFights(unittest.TestCase):
    def setUp(self):
        self.played = []
        player = lambda task: self.played.append(1) or True  # noqa: E731
        offer = lambda task: False  # noqa: E731
        handlers = {story_fights.SORTIE_PLAYER: player, story_fights.SORTIE_OFFER: offer}
        found = patch.object(story_fights, "sortie_handler", lambda name: handlers.get(name))
        found.start()
        self.addCleanup(found.stop)
        self.task, self.fight = FakeTask(), Fight()

    def step(self, now):
        return handle_story_fight_without_auto(self.task, self.fight.module, now=now)

    def test_an_idle_players_turn_is_taken_over(self):
        self.assertFalse(self.step(0))
        self.assertFalse(self.step(IDLE_SECONDS - 1))
        self.assertTrue(self.step(IDLE_SECONDS + 1))
        self.assertEqual(self.played, [1])
        self.assertTrue(any("takes it over" in line for line in self.task.logged))

    def test_a_fight_auto_is_playing_is_left_alone(self):
        for second in range(0, 60, 2):
            self.fight.count = 5 + second % 3
            self.assertFalse(self.step(second))
        self.assertEqual(self.played, [])

    def test_waiting_on_the_enemys_turn_is_not_idleness(self):
        self.task.finish_turn = False
        self.step(0)
        self.assertFalse(self.step(IDLE_SECONDS + 5))
        self.assertEqual(self.played, [])

    def test_once_taken_over_it_keeps_playing_then_hands_back(self):
        self.step(0)
        self.step(IDLE_SECONDS + 1)
        self.fight.count = 4
        self.assertTrue(self.step(IDLE_SECONDS + 2))
        self.fight.count = None
        self.assertFalse(self.step(IDLE_SECONDS + 3))
        self.assertFalse(self.step(IDLE_SECONDS + 4 + FIGHT_OVER_SECONDS))
        self.assertIsNone(getattr(self.task, STATE))


if __name__ == "__main__":
    unittest.main()
