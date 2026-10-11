"""Check that an edited handler module takes effect without restarting the app."""

import importlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import live  # noqa: E402


class TestLive(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        package = Path(self.folder.name) / "livepkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        self.source = package / "handlers_under_test.py"
        self.write("first")
        sys.path.insert(0, self.folder.name)
        self.addCleanup(sys.path.remove, self.folder.name)
        # As the app imports it: with bytecode written, which the first check reads the loaded source time from.
        with patch.object(sys, "dont_write_bytecode", False):
            self.module = importlib.import_module("livepkg.handlers_under_test")
        self.addCleanup(sys.modules.pop, "livepkg.handlers_under_test", None)
        self.addCleanup(sys.modules.pop, "livepkg", None)
        for name, value in (("PACKAGE", "livepkg"), ("LIVE_MODULES", ("handlers_under_test",)), ("_stamps", {}),
                            ("_last_check", 0.0)):
            patcher = patch.object(live, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, answer, bump=0):
        self.source.write_text(f"def handle(task):\n    return {answer!r}\n", encoding="utf-8")
        if bump:
            later = time.time() + bump
            os.utime(self.source, (later, later))

    def test_a_proxy_in_a_list_runs_the_edited_code_after_a_reload(self):
        entry = live.proxy("livepkg.handlers_under_test", "handle")
        self.assertEqual(entry.__name__, "handle")
        self.assertEqual(entry(None), "first")
        live.check(now=100)
        self.write("second", bump=5)
        importlib.invalidate_caches()
        self.assertEqual(live.check(now=200), ["handlers_under_test"])
        self.assertEqual(entry(None), "second")

    def test_an_edit_saved_before_the_first_check_is_still_loaded(self):
        entry = live.proxy("livepkg.handlers_under_test", "handle")
        self.write("second", bump=5)
        importlib.invalidate_caches()
        self.assertEqual(live.check(now=100), ["handlers_under_test"])
        self.assertEqual(entry(None), "second")

    def test_an_unchanged_module_is_left_alone(self):
        live.check(now=100)
        self.assertEqual(live.check(now=200), [])

    def test_a_broken_edit_keeps_the_old_code(self):
        entry = live.proxy("livepkg.handlers_under_test", "handle")
        live.check(now=100)
        self.source.write_text("def handle(task:\n", encoding="utf-8")
        later = time.time() + 5
        os.utime(self.source, (later, later))
        self.assertEqual(live.check(now=200), [])
        self.assertEqual(entry(None), "first")

    def test_checks_are_spaced_out(self):
        live.check(now=100)
        self.write("second", bump=5)
        self.assertEqual(live.check(now=100.5), [])


if __name__ == "__main__":
    unittest.main()
