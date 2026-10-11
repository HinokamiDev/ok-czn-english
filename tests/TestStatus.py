"""Check the status file an outside watcher reads, and that writing it can never stop a run."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import notify, status  # noqa: E402


class FakeTask:
    def __init__(self):
        self.name = "Chaos"
        self.node_status = {"total_rounds": 0, "success_rounds": 0, "pass_final_boss_count": 0}
        self.logged = []

    def log_info(self, message, notify=False):
        self.logged.append(message)

    def notification(self, *args, **kwargs):
        pass


class TaskDisabledException(Exception):
    pass


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "son-calisma.json"
        self.original = status.PATH
        status.PATH = self.path
        status._last_beat = 0.0
        self.task = FakeTask()

    def tearDown(self):
        status.PATH = self.original
        self.folder.cleanup()

    def test_run_lifecycle(self):
        status.event(self.task, "basladi", "Run started.")
        self.assertEqual(status.read()["durum"], "calisiyor")
        self.task.node_status.update(total_rounds=1, success_rounds=1)
        status.event(self.task, "kosu_bitti", "Run finished.")
        data = status.read()
        self.assertEqual((data["durum"], data["tur"], data["basarili"]), ("calisiyor", 1, 1))
        status.event(self.task, "takildi", "Stuck.")
        self.assertEqual(status.read()["durum"], "takildi")
        status.recovered(self.task)
        self.assertEqual(status.read()["durum"], "calisiyor")
        status.event(self.task, "durdu", "Run stopped.")
        data = status.read()
        self.assertEqual(data["durum"], "durdu")
        self.assertEqual([e["olay"] for e in data["olaylar"]], ["basladi", "kosu_bitti", "takildi", "durdu"])

    def test_new_start_clears_old_events_and_events_are_capped(self):
        for _ in range(status.MAX_EVENTS + 10):
            status.event(self.task, "kosu_bitti", "Run finished.")
        self.assertEqual(len(status.read()["olaylar"]), status.MAX_EVENTS)
        status.event(self.task, "basladi", "Run started.")
        self.assertEqual(len(status.read()["olaylar"]), 1)

    def test_error_survives_the_following_stop(self):
        def broken():
            raise ValueError("boom")

        run = status.watching(broken, self.task)
        with self.assertRaises(ValueError):
            run()
        status.stopping(lambda: None, self.task)()
        data = status.read()
        self.assertEqual(data["durum"], "hata")
        self.assertIn("boom", data["olaylar"][0]["mesaj"])

    def test_control_flow_exceptions_are_not_errors(self):
        status.event(self.task, "basladi", "Run started.")

        def stopped():
            raise TaskDisabledException()

        with self.assertRaises(TaskDisabledException):
            status.watching(stopped, self.task)()
        self.assertEqual(status.read()["durum"], "calisiyor")

    def test_heartbeat_only_refreshes_a_live_run(self):
        status.heartbeat(self.task, every=0)
        self.assertIsNone(status.read())
        status.event(self.task, "basladi", "Run started.")
        before = status.read()
        self.task.node_status["total_rounds"] = 3
        status.heartbeat(self.task, every=0)
        after = status.read()
        self.assertEqual(after["tur"], 3)
        self.assertEqual(len(after["olaylar"]), len(before["olaylar"]))

    def test_unwritable_path_never_raises(self):
        status.PATH = Path(self.folder.name) / "file"
        status.PATH.write_text("x")
        status.PATH = status.PATH / "inside" / "son-calisma.json"
        status.event(self.task, "basladi", "Run started.")
        status.heartbeat(self.task, every=0)

    def test_notifications_write_the_status(self):
        notify.announce(self.task, "Run started.", "basladi")
        self.assertEqual(status.read()["mesaj"], "Run started.")
        notify.announce(self.task, "Plain line.")
        self.assertEqual(status.read()["mesaj"], "Run started.")


if __name__ == "__main__":
    unittest.main()
