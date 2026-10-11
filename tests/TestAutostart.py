"""Check that a supervisor's start request starts the named mode once, and nothing starts without one."""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import autostart, status  # noqa: E402


class StoryMode:
    pass


class ChaosMode:
    pass


class SortieMode:
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

    def test_a_request_powershell_wrote_with_a_bom_is_read(self):
        # The supervisor's Set-Content -Encoding UTF8 writes this, and the first live restart dropped it.
        autostart.request_path().write_bytes(bytes([0xEF, 0xBB, 0xBF]) + b'{"mod": "StoryMode"}')
        autostart.start_requested(FakeExecutor(), self.controller)
        self.assertEqual(self.controller.started, ["StoryMode"])

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


class Mode:
    def __init__(self, name, enabled=False):
        self.__class__ = type(name, (Mode,), {})
        self.enabled = enabled

    def disable(self):
        self.enabled = False


class TestHandOver(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)
        self.story, self.chaos = Mode("StoryMode", enabled=True), Mode("ChaosMode")
        self.executor = types.SimpleNamespace(get_all_tasks=lambda: [self.story, self.chaos])
        self.controller = FakeController()
        self.controller.start = lambda task: (self.controller.started.append(task.__class__.__name__),
                                              setattr(task, "enabled", True))

    def test_story_hands_over_to_chaos_and_comes_back_after_the_run(self):
        autostart.request_switch("ChaosMode", then_story=True)
        autostart.poll(self.executor, self.controller)
        self.assertEqual((self.story.enabled, self.chaos.enabled), (False, True))
        # Still running: no return yet.
        self.assertIsNone(autostart.poll(self.executor, self.controller))
        self.chaos.enabled = False
        autostart.poll(self.executor, self.controller)
        self.assertEqual(self.controller.started, ["ChaosMode", "StoryMode"])
        self.assertTrue(self.story.enabled)
        self.assertIsNone(autostart.poll(self.executor, self.controller))

    def test_nothing_requested_does_nothing(self):
        self.assertIsNone(autostart.poll(self.executor, self.controller))
        self.assertEqual(self.controller.started, [])

    def test_no_return_before_the_awaited_run_has_begun(self):
        # Live: the app opened with nothing running and went straight back to Story, before Chaos started.
        self.story.enabled = False
        autostart.write_return("ChaosMode")
        self.assertIsNone(autostart.poll(self.executor, self.controller))
        self.assertEqual(self.controller.started, [])


if __name__ == "__main__":
    unittest.main()
