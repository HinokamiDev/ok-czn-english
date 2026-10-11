"""Check that Start and Resume put the game window back in front of the app."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en.shell import bring_game_forward, unpausing  # noqa: E402


class FakeTask:
    def __init__(self, fails=False):
        self.events = []
        self.fails = fails

    def unpause(self):
        self.events.append("unpause")

    def ensure_in_front(self):
        if self.fails:
            raise RuntimeError("no window")
        self.events.append("front")


class TestBringForward(unittest.TestCase):
    def test_resume_unpauses_then_brings_the_game_forward(self):
        task = FakeTask()
        unpausing(task)()
        self.assertEqual(task.events, ["unpause", "front"])

    def test_a_failure_to_bring_it_forward_does_not_stop_the_run(self):
        task = FakeTask(fails=True)
        unpausing(task)()
        bring_game_forward(task)
        self.assertEqual(task.events, ["unpause"])


if __name__ == "__main__":
    unittest.main()
