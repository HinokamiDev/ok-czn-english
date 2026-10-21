"""Check that menu commands from a file run one per frame, hold the mode off, and report what happened."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en import remote, status  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402


class FakeTask:
    width, height = 1920, 1080

    def __init__(self, boxes=()):
        self.all_texts = list(boxes)
        self.actions = []

    def click_relative(self, x, y):
        self.actions.append(("click", round(x, 3), round(y, 3)))

    def click_box(self, box):
        self.actions.append(("box", box.name))

    def move_relative(self, x, y):
        pass

    def send_key(self, key):
        self.actions.append(("key", key))

    def swipe_relative(self, x1, y1, x2, y2, duration=0, settle_time=0):
        self.actions.append(("drag", x1, y1, x2, y2, duration, settle_time))

    def sleep(self, seconds):
        pass

    def log_info(self, message):
        pass


class TestRemote(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = patch.object(status, "PATH", Path(folder.name) / "son-calisma.json")
        path.start()
        self.addCleanup(path.stop)

    def write(self, commands):
        remote.commands_path().write_text(json.dumps(commands), encoding="utf-8")

    def result(self):
        return json.loads(remote.result_path().read_text(encoding="utf-8"))

    def test_no_file_leaves_the_mode_alone(self):
        self.assertFalse(remote.step(FakeTask()))

    def test_commands_run_one_per_frame_then_hand_back(self):
        self.write([{"tikla": [0.5, 0.5]}, {"tus": "esc"}, {"surukle": [0.8, 0.5, 0.3, 0.5]}])
        task = FakeTask()
        self.assertTrue(remote.step(task))
        self.assertEqual(task.actions, [("click", 0.5, 0.5)])
        self.assertTrue(remote.step(task))
        self.assertTrue(remote.step(task))
        self.assertFalse(remote.commands_path().exists())
        self.assertFalse(remote.step(task))
        self.assertEqual(task.actions[1], ("key", "esc"))
        self.assertGreater(task.actions[2][-1], 0)
        self.assertEqual(self.result()["sonuc"], "done")

    def test_a_text_is_waited_for_then_clicked(self):
        self.write([{"tikla_metin": "Combatants", "bolge": [0.0, 0.0, 1.0, 1.0]}])
        task = FakeTask()
        self.assertTrue(remote.step(task))
        self.assertEqual(task.actions, [])
        task.all_texts = [FakeBox("Combatants", 0.7, 0.8, width=200)]
        self.assertTrue(remote.step(task))
        self.assertEqual(task.actions, [("box", "Combatants")])
        self.assertEqual(self.result()["sonuc"], "done")

    def test_a_text_never_seen_stops_the_list(self):
        self.write([{"tikla_metin": "Partners", "dene": 2}, {"tus": "esc"}])
        task = FakeTask()
        remote.step(task)
        remote.step(task)
        self.assertFalse(remote.commands_path().exists())
        self.assertIn("text not found", self.result()["sonuc"])
        self.assertEqual(task.actions, [])


    def test_a_hold_keeps_the_mode_waiting_until_the_file_is_replaced(self):
        self.write([{"tus": "esc"}, {"tut": True}])
        task = FakeTask()
        for _ in range(5):
            self.assertTrue(remote.step(task))
        self.assertTrue(remote.commands_path().exists())
        self.assertEqual(self.result()["sonuc"], "holding")
        self.assertEqual(task.actions, [("key", "esc")])
        self.write([{"tus": "f"}])
        self.assertTrue(remote.step(task))
        self.assertFalse(remote.commands_path().exists())

    def test_the_way_to_the_lobby_passes_the_title_and_the_pop_ups(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("TOUCH TO START", 0.5, 0.85, width=300)])
        remote.step(task)
        task.all_texts = [FakeBox("SKIP", 0.94, 0.05)]
        remote.step(task)
        task.all_texts = [FakeBox("点击屏幕关闭窗口", 0.5, 0.94, width=300)]
        remote.step(task)
        task.all_texts = [FakeBox("Notice", 0.215, 0.116), FakeBox("Update", 0.403, 0.119)]
        remote.step(task)
        self.assertTrue(remote.commands_path().exists())
        task.all_texts = [FakeBox("Simulation", 0.874, 0.353, width=200), FakeBox("Combatants", 0.868, 0.617, width=200)]
        remote.step(task)
        self.assertFalse(remote.commands_path().exists())
        self.assertEqual(task.actions, [("box", "TOUCH TO START"), ("box", "SKIP"), ("box", "点击屏幕关闭窗口"),
                                        ("click", 0.91, 0.119)])
        self.assertEqual(self.result()["sonuc"], "done")

    def test_a_chaos_result_screen_is_confirmed_on_the_way(self):
        # Live, 14 Oct: Story was started on the failed Chaos run's result screen and only tapped empty space.
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("Battle failed", 0.3, 0.717), FakeBox("Reward", 0.607, 0.626),
                         FakeBox("确认", 0.918, 0.918)])
        remote.step(task)
        self.assertEqual(task.actions, [("box", "确认")])
        task.all_texts = [FakeBox("Save Data collection complete", 0.5, 0.11), FakeBox("下一步", 0.935, 0.918)]
        remote.step(task)
        self.assertEqual(task.actions[-1], ("box", "下一步"))

    def test_a_menu_screen_is_left_by_its_back_arrow_but_the_lobby_corner_is_not(self):
        # Live, 14 Oct: Team Formation after the Chaos run, read as "主战员配置" beside the arrow.
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("主战员配置", 0.154, 0.043), FakeBox("The Blue Pot", 0.742, 0.154)])
        for _ in range(3):
            remote.step(task)
        self.assertIn(("click", 0.042, 0.044), task.actions)
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("LV", 0.054, 0.05), FakeBox("Amachan", 0.13, 0.055)])
        for _ in range(3):
            remote.step(task)
        self.assertNotIn(("click", 0.042, 0.044), task.actions)
        # As read live, 20 Oct: "LV" comes through the catalog as "等级".
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("等级", 0.054, 0.05), FakeBox("Amachan", 0.13, 0.054)])
        for _ in range(3):
            remote.step(task)
        self.assertNotIn(("click", 0.042, 0.044), task.actions)

    def test_agent_pins_are_found_under_their_hearts(self):
        import numpy as np
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for left, top in ((879, 365), (1180, 590)):
            frame[top:top + 30, left:left + 33] = (156, 111, 255)
        pins = remote.heart_pins(frame)
        self.assertEqual(len(pins), 2)
        self.assertAlmostEqual(pins[0][0], (879 + 16) / 1920 + 0.017, places=2)
        self.assertAlmostEqual(pins[0][1], (365 + 14.5) / 1080 + 0.045, places=2)
        self.write([{"kalp": 1}])
        task = FakeTask()
        task.frame = frame
        remote.step(task)
        self.assertEqual(task.actions[0][0], "click")
        self.assertAlmostEqual(task.actions[0][1], pins[1][0], places=2)

    def test_the_policy_nearest_the_targets_is_stamped(self):
        # As read live, 20 Oct (20261020-130045).
        boxes = [FakeBox("Activating Uniform Shield", 0.61, 0.22), FakeBox("2 Day(s) Reduced", 0.61, 0.315),
                 FakeBox("Increase Public Order", 0.59, 0.368), FakeBox("Index by 14", 0.55, 0.4),
                 FakeBox("Reduce Happiness by 3", 0.59, 0.453), FakeBox("Obtain Policy Point", 0.62, 0.507),
                 FakeBox("Partial Reinforced Shield", 0.86, 0.19), FakeBox("2 Day(s) Reduced", 0.85, 0.28),
                 FakeBox("Increase Public Order", 0.84, 0.335), FakeBox("Index by 8", 0.81, 0.363),
                 FakeBox("Increase Happiness by 2", 0.84, 0.42), FakeBox("Obtain Policy Point", 0.87, 0.475),
                 FakeBox("Happiness", 0.081, 0.634), FakeBox("60/100", 0.205, 0.634),
                 FakeBox("Administrative Index", 0.096, 0.723), FakeBox("97/100", 0.206, 0.724),
                 FakeBox("Economic Activity", 0.095, 0.814), FakeBox("60/100", 0.206, 0.816),
                 FakeBox("Public Order Index", 0.095, 0.904), FakeBox("37/100", 0.207, 0.908)]
        task = FakeTask(boxes)
        self.assertEqual(remote.policy_levels(task), {"Happiness": 60, "Administrative": 97, "Economic Activity": 60,
                                                      "Public Order": 37})
        self.assertEqual(remote.policy_effects(task, remote.POLICY_DOCUMENTS[0]), {"Public Order": 14, "Happiness": -3})
        self.write([{"politika": {"Public Order": 65, "Happiness": 60, "Economic Activity": 60}}])
        remote.step(task)
        self.assertEqual(task.actions[0][:5], ("drag", 0.735, 0.80, 0.61, 0.45))

    def test_a_menu_screen_never_gets_the_lobby_wake_up_tap(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("Simulation", 0.13, 0.047), FakeBox("Combat Training", 0.145, 0.69)])
        for _ in range(6):
            remote.step(task)
        self.assertNotIn(("click", 0.45, 0.8), task.actions)
        self.assertIn(("click", 0.042, 0.044), task.actions)

    def test_the_new_save_window_after_a_run_is_closed(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("Save Data", 0.234, 0.168), FakeBox("30270 TB", 0.33, 0.4),
                         FakeBox("Can Apply Mutation", 0.242, 0.818)])
        remote.step(task)
        self.assertEqual(task.actions, [("click", 0.881, 0.15)])
        # The Save Data page reads the same, but has Edit Data where the window's X would be.
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("Save Data", 0.36, 0.15), FakeBox("Can Apply Mutation", 0.37, 0.8),
                         FakeBox("Edit Data", 0.92, 0.158), FakeBox("Dismantle in Bulk", 0.5, 0.92)])
        remote.step(task)
        self.assertNotIn(("click", 0.881, 0.15), task.actions)

    def test_a_login_banner_is_closed_on_the_way(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("Seasonal", 0.132, 0.766), FakeBox("Rossweisse", 0.184, 0.827),
                         FakeBox("Seasonal Combatant Rescue Rate-Up", 0.234, 0.905), FakeBox("Go to Rescue", 0.897, 0.906)])
        remote.step(task)
        self.assertEqual(task.actions, [("click", 0.968, 0.052)])

    def test_the_anniversary_popup_is_closed(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("Instant giveaway of 5★ Combatant & Partner Selection Tickets to help you out!", 0.5, 0.275),
                         FakeBox("Visit the Nightmare Carnival right now!", 0.5, 0.846), FakeBox("Move", 0.555, 0.912)])
        remote.step(task)
        self.assertEqual(task.actions, [("click", 0.968, 0.052)])

    def test_a_season_introduction_is_confirmed(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask([FakeBox("New Season", 0.5, 0.278), FakeBox("Seasonal Power", 0.103, 0.756),
                         FakeBox("Season-Restricted", 0.897, 0.756), FakeBox("Confirm", 0.506, 0.931)])
        remote.step(task)
        self.assertEqual(task.actions, [("click", 0.5, 0.93)])

    def test_optional_steps_are_skipped_when_their_text_never_shows(self):
        self.write([{"varsa": "Notice", "tikla": [0.91, 0.119], "dene": 1},
                    {"tikla_metin": "SKIP", "istege_bagli": True, "dene": 1}, {"tus": "f"}])
        task = FakeTask()
        for _ in range(3):
            remote.step(task)
        self.assertEqual(task.actions, [("key", "f")])
        self.assertEqual(self.result()["sonuc"], "done")

    def test_a_click_only_when_a_text_is_missing(self):
        self.write([{"yoksa": "Simulation", "tikla": [0.042, 0.044]}, {"yoksa": "Simulation", "tikla": [0.5, 0.5]}])
        task = FakeTask()
        remote.step(task)
        task.all_texts = [FakeBox("Simulation", 0.874, 0.353, width=200)]
        remote.step(task)
        self.assertEqual(task.actions, [("click", 0.042, 0.044)])

    def test_a_lobby_with_its_menus_hidden_is_tapped_awake(self):
        self.write([{"lobiye_don": True}])
        task = FakeTask()
        for _ in range(3):
            remote.step(task)
        self.assertEqual(task.actions, [("click", 0.45, 0.8)])
        task.all_texts = [FakeBox("Simulation", 0.874, 0.353, width=200), FakeBox("Combatants", 0.868, 0.617, width=200)]
        remote.step(task)
        self.assertFalse(remote.commands_path().exists())

if __name__ == "__main__":
    unittest.main()
