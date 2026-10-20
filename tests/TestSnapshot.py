"""Check the stuck-screen snapshot: saved once a picture holds still long enough, once per spell, never while asking."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import snapshot, status  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402


class FakeTask:
    name = "半自动剧情模式"
    width, height = 1920, 1080

    def __init__(self):
        self.frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        self.all_texts = [FakeBox("Skip", 0.8, 0.05)]
        self.logged = []

    def log_info(self, message):
        self.logged.append(message)


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)
        self.task = FakeTask()

    def saved(self):
        return sorted(snapshot.folder().glob("*.png")) if snapshot.folder().exists() else []

    def test_a_still_screen_is_saved_once_with_its_text(self):
        snapshot.check(self.task, now=0)
        snapshot.check(self.task, now=snapshot.STILL_SECONDS - 1)
        self.assertEqual(self.saved(), [])
        snapshot.check(self.task, now=snapshot.STILL_SECONDS + 1)
        snapshot.check(self.task, now=snapshot.STILL_SECONDS + 30)
        self.assertEqual(len(self.saved()), 1)
        record = json.loads(self.saved()[0].with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(record["metinler"][0]["metin"], "Skip")
        self.assertEqual(status.read()["durum"], "takildi")
        self.assertIn(str(self.saved()[0]), status.read()["mesaj"])

    def test_a_moving_screen_is_never_saved(self):
        for second in range(0, 120, 5):
            self.task.frame = np.full((1080, 1920, 3), (second * 7) % 255, dtype=np.uint8)
            self.task.all_texts = [FakeBox(f"line {chr(65 + second % 26)}", 0.5, 0.8)]
            snapshot.check(self.task, now=second)
        self.assertEqual(self.saved(), [])

    def test_a_new_spell_after_movement_is_saved_again(self):
        snapshot.check(self.task, now=0)
        snapshot.check(self.task, now=30)
        self.task.frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
        snapshot.check(self.task, now=31)
        snapshot.check(self.task, now=60)
        self.assertEqual(len(self.saved()), 2)

    def test_waiting_for_an_answer_is_not_stuck(self):
        setattr(self.task, snapshot.ASKING, {"id": "x"})
        snapshot.check(self.task, now=0)
        snapshot.check(self.task, now=100)
        self.assertEqual(self.saved(), [])


class TestActions(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)
        self.task = FakeTask()

    def moving(self, second):
        self.task.frame = np.full((1080, 1920, 3), (second * 13) % 255, dtype=np.uint8)
        self.task.all_texts = [FakeBox(f"line {chr(65 + second % 26)}", 0.5, 0.8)]

    def test_the_same_action_over_and_over_is_saved(self):
        # Live: "e" sent every 3s while a box refused it, the screen and the hand's OCR changing all the while.
        actions = self.task.__dict__.setdefault(snapshot.ACTIONS, snapshot.deque(maxlen=16))
        for second in range(0, 30, 3):
            actions.append((second, "key", "e"))
            self.moving(second)
            snapshot.check(self.task, now=second)
        self.assertEqual(len(list(snapshot.folder().glob("*.png"))), 1)
        self.assertIn("Same key e repeated", status.read()["mesaj"])

    def test_varied_actions_are_not_a_loop(self):
        actions = self.task.__dict__.setdefault(snapshot.ACTIONS, snapshot.deque(maxlen=16))
        for second in range(0, 60, 3):
            actions.append((second, "key", str(second % 5)))
            self.moving(second)
            snapshot.check(self.task, now=second)
        self.assertFalse(snapshot.folder().exists() and list(snapshot.folder().glob("*.png")))

    def test_nothing_sent_for_long_is_saved_even_on_a_moving_screen(self):
        for second in range(0, snapshot.IDLE_SECONDS + 10, 5):
            self.moving(second)
            snapshot.check(self.task, now=second)
        self.assertEqual(len(list(snapshot.folder().glob("*.png"))), 1)
        self.assertIn("No click or key", status.read()["mesaj"])

    def test_a_mode_started_again_after_a_break_is_not_idle_at_once(self):
        actions = self.task.__dict__.setdefault(snapshot.ACTIONS, snapshot.deque(maxlen=16))
        actions.append((0, "click", "@1,1"))
        self.moving(0)
        snapshot.check(self.task, now=0)
        # Stopped for a hand-over, started again fifteen minutes later.
        self.moving(900)
        snapshot.check(self.task, now=900)
        self.assertFalse(snapshot.folder().exists() and list(snapshot.folder().glob("*.png")))

    def test_clicks_on_boxes_are_described_by_name_and_place(self):
        self.assertEqual(snapshot.describe_click((FakeBox("确认", 0.5, 0.5),), {}), "确认@45,26")
        self.assertEqual(snapshot.describe_click((1532, 59), {}), "@76,2")


class TestOnRequest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)

    def test_a_requested_snapshot_is_taken_at_once_and_the_request_cleared(self):
        task = FakeTask()
        request = status.PATH.parent / snapshot.REQUEST_NAME
        request.write_text("", encoding="utf-8")
        snapshot.check(task, now=0)
        self.assertEqual(len(list(snapshot.folder().glob("*.png"))), 1)
        self.assertFalse(request.exists())
        self.assertIn("on request", status.read()["mesaj"])


class TestTextStill(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)
        self.task = FakeTask()

    def moving(self, second):
        # Characters on a story scene keep moving, so the picture changes every frame.
        self.task.frame = np.full((1080, 1920, 3), (second * 13) % 255, dtype=np.uint8)

    def test_a_moving_scene_with_the_same_text_is_saved(self):
        for second in range(0, snapshot.TEXT_STILL_SECONDS + 10, 5):
            self.moving(second)
            snapshot.check(self.task, now=second)
        self.assertEqual(len(list(snapshot.folder().glob("*.png"))), 1)
        self.assertIn("Text on screen unchanged", status.read()["mesaj"])

    def test_text_that_keeps_changing_is_not_stuck(self):
        for second in range(0, 120, 5):
            self.moving(second)
            self.task.all_texts = [FakeBox(f"line {chr(65 + second % 26)}", 0.5, 0.8)]
            snapshot.check(self.task, now=second)
        self.assertFalse(snapshot.folder().exists() and list(snapshot.folder().glob("*.png")))

    def test_a_ticking_number_alone_is_not_movement(self):
        for second in range(0, snapshot.TEXT_STILL_SECONDS + 10, 5):
            self.moving(second)
            self.task.all_texts = [FakeBox(f"Turn {second}", 0.5, 0.8)]
            snapshot.check(self.task, now=second)
        self.assertEqual(len(list(snapshot.folder().glob("*.png"))), 1)



class TestGuardedClick(unittest.TestCase):
    def test_a_refused_pointer_loses_the_click_not_the_run(self):
        def refused(operation, *args, **kwargs):
            raise OSError(0, "SetCursorPos", "No error message is available")
        self.assertFalse(snapshot.guarded_click(refused, None, (1, 2), {}))

    def test_other_errors_still_raise(self):
        def broken(operation, *args, **kwargs):
            raise ValueError("other")
        with self.assertRaises(ValueError):
            snapshot.guarded_click(broken, None, (), {})


if __name__ == "__main__":
    unittest.main()
