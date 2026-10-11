"""Check that a supervisor's start request starts the named mode once, and nothing starts without one."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import autostart, status  # noqa: E402


class StoryMode:
    pass


class ChaosMode:
    pass


class FakeExecutor:
    def __init__(self):
        self.tasks = [ChaosMode(), StoryMode()]

    def get_all_tasks(self):
        return list(self.tasks)


class FakeController:
    def __init__(self):
        self.started = []

    def start(self, task):
        self.started.append(task.__class__.__name__)


class TestAutostart(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)
        self.controller = FakeController()

    def request(self, mode):
        autostart.request_path().write_text(json.dumps({"mod": mode}), encoding="utf-8")

    def test_the_named_mode_starts_once(self):
        self.request("StoryMode")
        autostart.start_requested(FakeExecutor(), self.controller)
        autostart.start_requested(FakeExecutor(), self.controller)
        self.assertEqual(self.controller.started, ["StoryMode"])
        self.assertFalse(autostart.request_path().exists())

    def test_the_status_files_chinese_name_is_accepted(self):
        self.request("自动卡厄思模式")
        autostart.start_requested(FakeExecutor(), self.controller)
        self.assertEqual(self.controller.started, ["ChaosMode"])

    def test_no_request_starts_nothing(self):
        self.assertIsNone(autostart.start_requested(FakeExecutor(), self.controller))
        self.assertEqual(self.controller.started, [])

    def test_an_unknown_or_broken_request_is_dropped(self):
        self.request("Rm -rf")
        autostart.start_requested(FakeExecutor(), self.controller)
        autostart.request_path().write_text("{not json", encoding="utf-8")
        autostart.start_requested(FakeExecutor(), self.controller)
        self.assertEqual(self.controller.started, [])
        self.assertFalse(autostart.request_path().exists())


if __name__ == "__main__":
    unittest.main()
