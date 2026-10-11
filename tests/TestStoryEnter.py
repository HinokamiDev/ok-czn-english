"""Check that the Story mode presses a stage's Enter button on the Global client.

Live: the stage panel for Chapter 5 #07 Epilogue stayed open while the Story mode clicked the #07 node again every
four seconds, because upstream only knew the Chinese caption 入场.
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en.story_enter import BUTTON_POINT, handle_skip_dialogue_confirm, pressing_enter  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402

WIDTH, HEIGHT = 1920, 1080


class FakeTask:
    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes
        self.clicked = []
        self.logged = []

    def click_box(self, box):
        self.clicked.append(box.name)

    def sleep(self, seconds):
        pass

    def log_info(self, message):
        self.logged.append(message)


def find_box_at_point(task, rel_x, rel_y):
    px, py = rel_x * task.width, rel_y * task.height
    hits = [b for b in task.all_texts if b.x <= px <= b.x + b.width and b.y <= py <= b.y + b.height]
    return min(hits, key=lambda b: b.area()) if hits else None


UTILS = types.SimpleNamespace(find_box_at_point=find_box_at_point,
                              _clean_match=lambda text, target: text.strip() == target)


class TestStoryEnter(unittest.TestCase):
    def setUp(self):
        self.upstream = []
        self.handler = pressing_enter(lambda task: self.upstream.append(task) or False, UTILS)

    def test_the_global_caption_is_pressed(self):
        # Where the live screenshot showed it: about x 0.795-0.840, y 0.925-0.953.
        task = FakeTask([FakeBox("进入", 0.818, 0.939, width=90, height=32)])
        self.assertTrue(self.handler(task))
        self.assertEqual(task.clicked, ["进入"])

    def test_an_untranslated_reading_still_counts(self):
        task = FakeTask([FakeBox("Enter", *BUTTON_POINT)])
        self.assertTrue(self.handler(task))

    def test_upstreams_caption_is_left_to_upstream(self):
        task = FakeTask([FakeBox("入场", *BUTTON_POINT)])
        self.assertFalse(self.handler(task))
        self.assertEqual((task.clicked, len(self.upstream)), ([], 1))

    def test_other_text_there_is_not_pressed(self):
        task = FakeTask([FakeBox("Reward", *BUTTON_POINT)])
        self.assertFalse(self.handler(task))
        self.assertEqual(task.clicked, [])


class TestSkipDialogueConfirm(unittest.TestCase):
    # Read off the live snapshot 20261011-184545.
    LIVE = [FakeBox("Do you want to skip the current dialogue?", 0.501, 0.314, width=700),
            FakeBox("Do not show until next login", 0.519, 0.575, width=400),
            FakeBox("取消", 0.348, 0.684), FakeBox("确认", 0.666, 0.683)]

    def test_the_skip_question_is_confirmed(self):
        task = FakeTask(list(self.LIVE))
        self.assertTrue(handle_skip_dialogue_confirm(task))
        self.assertEqual(task.clicked, ["确认"])

    def test_without_the_question_nothing_is_pressed(self):
        task = FakeTask([FakeBox("确认", 0.666, 0.683)])
        self.assertFalse(handle_skip_dialogue_confirm(task))
        self.assertEqual(task.clicked, [])


if __name__ == "__main__":
    unittest.main()
