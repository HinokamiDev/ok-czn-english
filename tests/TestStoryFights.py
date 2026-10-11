"""Check when the Story mode takes a fight over with the Sortie card player, and when it hands it back."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import story_fights  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402
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
        # Upstream returns OCR boxes, as the live crash showed, so the fake does too.
        self.module = types.SimpleNamespace(_read_hand_count=lambda task: self.count,
                                            _hand_card_names=lambda task: [FakeBox(name, 0.3, 0.85)
                                                                           for name in self.names or []])


class TestStoryFights(unittest.TestCase):
    def setUp(self):
        self.played = []
        player = lambda task: self.played.append(1) or True  # noqa: E731
        offer = lambda task: False  # noqa: E731
        handlers = {story_fights.SORTIE_PLAYER: player, story_fights.SORTIE_OFFER: offer,
                    story_fights.SORTIE_HAND_PICK: lambda task: False}
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


class CardsLeftTask(FakeTask):
    width, height = 1920, 1080

    def __init__(self, boxes):
        super().__init__()
        self.all_texts = boxes
        self.clicked = []

    def click_box(self, box):
        self.clicked.append(box.name)

    def sleep(self, seconds):
        pass


class TestCardsLeft(unittest.TestCase):
    # Snapshot 20261011-200656.
    LIVE = [FakeBox("Cards in your hand can still be used.", 0.5, 0.358, width=500),
            FakeBox("Do you wish to end your turn without using them?", 0.501, 0.395, width=600),
            FakeBox("取消", 0.347, 0.604), FakeBox("确认", 0.667, 0.604)]

    def turn_with_refusals(self, task):
        from src.en.battle import TURN, Turn
        turn = Turn(4)
        turn.refused.update({"Fatal Strike", "Experienced Strike"})
        setattr(task, TURN, turn)
        return turn

    def test_refusals_from_a_speech_box_are_cancelled_once(self):
        task = CardsLeftTask(list(self.LIVE))
        turn = self.turn_with_refusals(task)
        setattr(task, story_fights.DIALOGUE_PRESSED, ("There's an opening near the head!", 10.0))
        with patch.object(story_fights.time, "monotonic", return_value=20.0):
            self.assertTrue(story_fights.answer_cards_left(task, 20.0))
        self.assertEqual(task.clicked, ["取消"])
        self.assertEqual(turn.refused, set())
        turn.refused.add("Fatal Strike")
        self.assertTrue(story_fights.answer_cards_left(task, 30.0))
        self.assertEqual(task.clicked, ["取消", "确认"])

    def test_an_end_chosen_on_purpose_is_confirmed(self):
        task = CardsLeftTask(list(self.LIVE))
        self.assertTrue(story_fights.answer_cards_left(task, 0))
        self.assertEqual(task.clicked, ["确认"])

    def test_without_the_question_nothing_happens(self):
        task = CardsLeftTask([FakeBox("确认", 0.667, 0.604)])
        self.assertFalse(story_fights.answer_cards_left(task, 0))


class TestHandPick(unittest.TestCase):
    def test_a_hand_pick_prompt_goes_to_upstreams_picker(self):
        picked = []
        handlers = {story_fights.SORTIE_HAND_PICK: lambda task: picked.append(1) or True}
        task = CardsLeftTask([FakeBox("请选择1张卡牌", 0.517, 0.11), FakeBox("0/1", 0.499, 0.169)])
        with patch.object(story_fights, "sortie_handler", lambda name: handlers.get(name)):
            self.assertTrue(handle_story_fight_without_auto(task, Fight().module, now=0))
        self.assertEqual(picked, [1])


class TestNeverStopsTheRun(unittest.TestCase):
    def test_a_fault_costs_the_frame_not_the_run(self):
        broken = types.SimpleNamespace(_read_hand_count=lambda task: 1 / 0)
        self.assertFalse(handle_story_fight_without_auto(FakeTask(), broken, now=0))


class TestOcrNoise(unittest.TestCase):
    def test_names_read_differently_each_frame_do_not_hide_an_idle_fight(self):
        played = []
        handlers = {story_fights.SORTIE_PLAYER: lambda task: played.append(1) or True,
                    story_fights.SORTIE_OFFER: lambda task: False}
        with patch.object(story_fights, "sortie_handler", lambda name: handlers.get(name)):
            task, fight = FakeTask(), Fight()
            # The live run read one 5-card hand as these, frame after frame.
            readings = [["onclad)", "Experienced Strik", "Fatal Strike", "Fighting Spirit"],
                        ["Fatal Strike", "Fighting Spirit"], ["Experienced Strik", "Fatal Strike", "Fighting Spirit"]]
            for second in range(0, IDLE_SECONDS + 4, 2):
                fight.names = readings[second % 3]
                handle_story_fight_without_auto(task, fight.module, now=second)
        self.assertTrue(played)


if __name__ == "__main__":
    unittest.main()
