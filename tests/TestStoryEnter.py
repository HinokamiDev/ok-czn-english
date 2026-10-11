"""Check that the Story mode presses a stage's Enter button on the Global client.

Live: the stage panel for Chapter 5 #07 Epilogue stayed open while the Story mode clicked the #07 node again every
four seconds, because upstream only knew the Chinese caption 入场.
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en.story_enter import (  # noqa: E402
    BUTTON_POINT, handle_skip_dialogue_confirm, handle_story_event_option, pressing_auto_chat_once, pressing_enter,
)
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

    def test_the_taller_box_with_main_characters_is_confirmed_too(self):
        # Snapshot 20261011-212858.
        task = FakeTask([FakeBox("Do you want to skip the current dialogue?", 0.5, 0.212, width=700),
                         FakeBox("Main Characters", 0.501, 0.444), FakeBox("取消", 0.346, 0.784),
                         FakeBox("确认", 0.662, 0.786)])
        self.assertTrue(handle_skip_dialogue_confirm(task))
        self.assertEqual(task.clicked, ["确认"])

    def test_the_act_4_wording_lower_down_is_confirmed(self):
        # Snapshot 20261011-221553.
        task = FakeTask([FakeBox("Do you want to skip this story?", 0.502, 0.41, width=500),
                         FakeBox("Do not show until next login", 0.52, 0.53, width=400),
                         FakeBox("取消", 0.347, 0.632), FakeBox("确认", 0.666, 0.632)])
        self.assertTrue(handle_skip_dialogue_confirm(task))
        self.assertEqual(task.clicked, ["确认"])

    def test_a_misread_last_word_still_counts(self):
        # Snapshot 20261011-213047.
        task = FakeTask([FakeBox("Do you want to skip the current dlialogue?", 0.5, 0.212, width=700),
                         FakeBox("取消", 0.347, 0.785), FakeBox("确认", 0.69, 0.784)])
        self.assertTrue(handle_skip_dialogue_confirm(task))

    def test_without_the_question_nothing_is_pressed(self):
        task = FakeTask([FakeBox("确认", 0.666, 0.683)])
        self.assertFalse(handle_skip_dialogue_confirm(task))
        self.assertEqual(task.clicked, [])


class TestAutoChatOnce(unittest.TestCase):
    def test_the_toggle_is_pressed_once_not_four_times(self):
        presses = []
        handler = pressing_auto_chat_once(lambda task: presses.append(1) or True)
        task = FakeTask([])
        # The live run pressed it at 30.679, 32.213, 33.701 and 35.262.
        results = [handler(task) for _ in range(4)]
        self.assertEqual((results, len(presses)), ([True, False, False, False], 1))

    def test_nothing_pressed_starts_no_cooldown(self):
        presses = []
        handler = pressing_auto_chat_once(lambda task: presses.append(1) or False)
        task = FakeTask([])
        handler(task)
        handler(task)
        self.assertEqual(len(presses), 2)


NO_FIGHT = types.SimpleNamespace(_read_hand_count=lambda task: None)
IN_FIGHT = types.SimpleNamespace(_read_hand_count=lambda task: 5)


class TestStoryEventOption(unittest.TestCase):
    # Read off the live snapshot 20261011-192220.
    LIVE = [FakeBox("356/356", 0.211, 0.038),
            FakeBox("To rescue Nine's companion, 'Alcea',", 0.501, 0.21, width=500),
            FakeBox("Enter the ventilation shaft", 0.475, 0.798, width=320),
            FakeBox("Event Encounter: Rescue Alcea", 0.502, 0.836, width=380)]

    def test_the_offered_step_is_pressed_on_its_title(self):
        task = FakeTask(list(self.LIVE))
        self.assertTrue(handle_story_event_option(task, NO_FIGHT))
        self.assertEqual(task.clicked, ["Enter the ventilation shaft"])

    def test_it_is_not_pressed_again_at_once(self):
        task = FakeTask(list(self.LIVE))
        handle_story_event_option(task, NO_FIGHT)
        self.assertFalse(handle_story_event_option(task, NO_FIGHT))

    def test_an_option_without_an_encounter_line_on_a_walk_is_pressed(self):
        task = FakeTask([FakeBox("356/356", 0.211, 0.038), FakeBox("Examine the rubble", 0.5, 0.8)])
        self.assertTrue(handle_story_event_option(task, NO_FIGHT))
        self.assertEqual(task.clicked, ["Examine the rubble"])

    def test_text_in_the_band_off_a_walk_is_left_alone(self):
        task = FakeTask([FakeBox("Examine the rubble", 0.5, 0.8)])
        self.assertFalse(handle_story_event_option(task, NO_FIGHT))

    def test_a_hand_with_its_counter_misread_is_not_an_option(self):
        # Live: the counter went unread and the hand's names were pressed every six seconds.
        task = FakeTask([FakeBox("1977/1977", 0.212, 0.038), FakeBox("Dual Creatior", 0.578, 0.75),
                         FakeBox("Upgrad", 0.571, 0.773)])
        self.assertFalse(handle_story_event_option(task, NO_FIGHT))

    def test_a_fights_hand_is_never_taken_for_options(self):
        task = FakeTask([FakeBox("1567 / 1567", 0.2, 0.04), FakeBox("Fatal Strike", 0.45, 0.85)])
        self.assertFalse(handle_story_event_option(task, IN_FIGHT))
        self.assertEqual(task.clicked, [])


class TestMagnifier(unittest.TestCase):
    def test_the_live_magnifier_is_found_at_its_drawn_size(self):
        import cv2
        import numpy as np
        from src.en.story_enter import find_magnifier

        crop = cv2.imread(str(Path(__file__).resolve().parent / "images" / "story_walk_magnifier.png"))
        # Put the live crop back where it was cut from, on a full 1920x1080 frame.
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[300:700, 1000:1450] = crop
        found = find_magnifier(frame)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], 1232 / 1920, delta=0.01)
        self.assertAlmostEqual(found[1], 467 / 1080, delta=0.01)

    def test_an_empty_frame_has_none(self):
        import numpy as np
        from src.en.story_enter import find_magnifier

        self.assertIsNone(find_magnifier(np.zeros((1080, 1920, 3), dtype=np.uint8)))


class TestWalkDialogue(unittest.TestCase):
    # Read off the live snapshot 20261011-192925.
    LIVE = [FakeBox("356/356", 0.211, 0.038), FakeBox("□", 0.107, 0.089),
            FakeBox("Isn't this just a pillar?", 0.182, 0.203, width=300)]

    def test_the_line_is_clicked_on(self):
        from src.en.story_enter import handle_story_walk_dialogue
        task = FakeTask(list(self.LIVE))
        self.assertTrue(handle_story_walk_dialogue(task, NO_FIGHT))
        self.assertEqual(task.clicked, ["Isn't this just a pillar?"])
        self.assertFalse(handle_story_walk_dialogue(task, NO_FIGHT))

    def test_a_cut_in_without_the_health_bar_is_clicked_too(self):
        from src.en.story_enter import handle_story_walk_dialogue
        # Snapshot 20261011-193511: the only text on screen.
        task = FakeTask([FakeBox("We need to target its arms first.", 0.219, 0.204, width=380)])
        self.assertTrue(handle_story_walk_dialogue(task, NO_FIGHT))

    def test_a_fight_waiting_on_the_box_is_clicked_on_too(self):
        from src.en.story_enter import handle_story_walk_dialogue
        # Snapshot 20261011-200343: mid-fight, the cards and the end-turn key were refused until this was clicked.
        task = FakeTask([FakeBox("354 /475", 0.211, 0.036), FakeBox("There's an opening near the head!", 0.23, 0.205,
                                                                     width=400),
                         FakeBox("Fatal Strike", 0.43, 0.748), FakeBox("04/10", 0.501, 0.97)])
        self.assertTrue(handle_story_walk_dialogue(task, IN_FIGHT))
        self.assertEqual(task.clicked, ["There's an opening near the head!"])


class TestStageComplete(unittest.TestCase):
    def test_the_complete_banner_is_tapped(self):
        from src.en.story_enter import handle_story_walk_dialogue
        # Snapshot 20261011-201125.
        task = FakeTask([FakeBox("故事", 0.106, 0.048), FakeBox("01", 0.501, 0.375),
                         FakeBox("Warriors of the Arena", 0.501, 0.5, width=300), FakeBox("Complete", 0.499, 0.568)])
        self.assertTrue(handle_story_walk_dialogue(task, NO_FIGHT))
        self.assertEqual(task.clicked, ["Complete"])

    def test_complete_inside_a_sentence_is_not_the_banner(self):
        from src.en.story_enter import handle_stage_complete
        task = FakeTask([FakeBox("Quest Complete soon", 0.5, 0.56)])
        self.assertFalse(handle_stage_complete(task))


class MapTask(FakeTask):
    def __init__(self, boxes, entrances=False):
        super().__init__(boxes)
        self.entrances = entrances

    def box_of_screen(self, *region):
        return region

    def find_feature(self, feature_name=None, box=None, **kwargs):
        return [object()] if self.entrances else []


class TestNextChapter(unittest.TestCase):
    # Snapshot 20261011-201244.
    LIVE = [FakeBox("故事", 0.106, 0.047), FakeBox("Chapter 1", 0.403, 0.04), FakeBox("After the Battle", 0.197, 0.435),
            FakeBox("#09", 0.271, 0.504), FakeBox("02", 0.905, 0.471),
            FakeBox("Desert Kingdom Ruins", 0.809, 0.532, width=300)]

    def test_a_finished_map_moves_on(self):
        from src.en.story_enter import handle_next_chapter
        task = MapTask(list(self.LIVE) + [FakeBox("Chapter 2", 0.606, 0.04)])
        self.assertTrue(handle_next_chapter(task))
        self.assertEqual(task.clicked, ["Chapter 2"])

    def test_without_the_tab_the_arrow_is_pressed(self):
        from src.en.story_enter import NEXT_CHAPTER_ARROW, handle_next_chapter
        task = MapTask(list(self.LIVE))
        pressed = []
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertTrue(handle_next_chapter(task))
        self.assertEqual(pressed, [NEXT_CHAPTER_ARROW])

    def test_a_stage_still_to_enter_comes_first(self):
        from src.en.story_enter import handle_next_chapter
        task = MapTask(list(self.LIVE), entrances=True)
        self.assertFalse(handle_next_chapter(task))


class TestWrappedLines(unittest.TestCase):
    def test_a_line_wrapped_to_three_is_clicked_on(self):
        from src.en.story_enter import handle_story_walk_dialogue
        # Snapshot 20261011-202512.
        task = FakeTask([FakeBox("Ah..? I don't know why, but..", 0.209, 0.169, width=330),
                         FakeBox("it feels like the magical power has", 0.227, 0.205, width=380),
                         FakeBox("weakened..!", 0.154, 0.239, width=150)])
        self.assertTrue(handle_story_walk_dialogue(task, NO_FIGHT))


class TestSpeechBoxFrame(unittest.TestCase):
    """Crops of live captures, put back on a 1280x720 frame: the "… …" box, a walk without one, a bright map."""

    def frame(self, name):
        import cv2
        import numpy as np
        crop = cv2.imread(str(Path(__file__).resolve().parent / "images" / name))
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[0:crop.shape[0], 0:crop.shape[1]] = crop
        return frame

    def test_the_box_is_seen_without_any_text(self):
        from src.en.story_enter import speech_box_on_screen
        self.assertTrue(speech_box_on_screen(self.frame("speech_box_dots.png")))
        # Act 4 Chapter 3: a dark box on a bright sky, no rule along its edges.
        self.assertTrue(speech_box_on_screen(self.frame("speech_box_bright_scene.png")))

    def test_no_box_on_a_dark_walk_or_a_bright_map(self):
        from src.en.story_enter import speech_box_on_screen
        self.assertFalse(speech_box_on_screen(self.frame("speech_box_none.png")))
        self.assertFalse(speech_box_on_screen(self.frame("speech_box_none_bright.png")))

    def test_chaos_and_sortie_click_a_box_seen_by_its_frame(self):
        from src.en.story_enter import BOX_CENTRE, handle_fork_steps
        task = FakeTask([])
        task.frame = self.frame("speech_box_dots.png")
        pressed = []
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertTrue(handle_fork_steps(task))
        self.assertEqual(pressed, [BOX_CENTRE])
        empty = FakeTask([])
        empty.frame = self.frame("speech_box_none.png")
        self.assertFalse(handle_fork_steps(empty))

    def test_an_unread_box_is_clicked_on(self):
        from src.en.story_enter import BOX_CENTRE, handle_story_walk_dialogue
        task = FakeTask([])
        task.frame = self.frame("speech_box_dots.png")
        pressed = []
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertTrue(handle_story_walk_dialogue(task, NO_FIGHT))
        self.assertEqual(pressed, [BOX_CENTRE])


class TestMapDrag(unittest.TestCase):
    # Snapshot 20261011-203637.
    LIVE = [FakeBox("故事", 0.106, 0.047), FakeBox("Chapter 3", 0.473, 0.04), FakeBox("Continued Advance", 0.212, 0.436),
            FakeBox("#06(", 0.274, 0.503), FakeBox("#", 0.987, 0.503, width=20), FakeBox("#06-1", 0.532, 0.657)]

    def test_a_stage_cut_off_on_the_right_is_dragged_into_view(self):
        from src.en.story_enter import MAP_DRAG, handle_map_drag
        task = MapTask(list(self.LIVE))
        swipes = []
        task.swipe_relative = lambda x1, y1, x2, y2, duration=0: swipes.append(((x1, y1), (x2, y2)))
        self.assertTrue(handle_map_drag(task))
        self.assertEqual(swipes, [MAP_DRAG])

    def test_a_name_cut_off_at_the_edge_is_dragged_into_view_too(self):
        from src.en.story_enter import handle_map_drag
        # Snapshot 20261011-212746.
        task = MapTask([FakeBox("故事", 0.106, 0.047), FakeBox("Chapter 3", 0.452, 0.04),
                        FakeBox("Toward the Abyss", 0.571, 0.493), FakeBox("The B", 0.967, 0.436, width=50)])
        swipes = []
        task.swipe_relative = lambda x1, y1, x2, y2, duration=0: swipes.append(1)
        self.assertTrue(handle_map_drag(task))
        self.assertEqual(swipes, [1])

    def test_a_visible_play_button_is_entered_instead(self):
        from src.en.story_enter import handle_map_drag
        task = MapTask(list(self.LIVE), entrances=True)
        self.assertFalse(handle_map_drag(task))


class TestObserveStage(unittest.TestCase):
    def test_a_chaos_stage_is_entered_and_handed_to_the_chaos_mode(self):
        import tempfile
        from unittest.mock import patch
        from src.en import autostart, status
        from src.en.story_enter import handle_observe_stage
        with tempfile.TemporaryDirectory() as folder,                 patch.object(status, "PATH", Path(folder) / "son-calisma.json"):
            # Snapshot 20261011-203734.
            task = MapTask([FakeBox("Chapter 3", 0.439, 0.04), FakeBox("#07", 0.479, 0.504),
                            FakeBox("Observe", 0.567, 0.504)])
            self.assertTrue(handle_observe_stage(task))
            self.assertEqual(task.clicked, ["Observe"])
            folder_path = Path(folder)
            self.assertTrue((folder_path / autostart.SWITCH_NAME).exists())
            self.assertTrue((folder_path / autostart.RETURN_NAME).exists())


class TestStepFailure(unittest.TestCase):
    def test_a_failing_step_does_not_stop_the_run(self):
        from unittest.mock import patch
        from src.en import story_enter

        def broken(task, utils_sortie=None):
            raise AttributeError("module has no attribute 'request_switch'")

        with patch.object(story_enter, "STORY_STEPS", ("broken_step",)),                 patch.dict(story_enter.__dict__, {"broken_step": broken}):
            self.assertFalse(story_enter.handle_story_walk_dialogue(FakeTask([]), NO_FIGHT))


class TestTitleScreen(unittest.TestCase):
    def test_the_title_screen_is_touched(self):
        from src.en.story_enter import handle_fork_steps
        # As OCR read it on the live title screen, spaces and all gone.
        task = FakeTask([FakeBox("TOUCHTOSTART", 0.501, 0.80, width=320), FakeBox("Repair Resources", 0.124, 0.888)])
        task.frame = None
        self.assertTrue(handle_fork_steps(task))
        self.assertEqual(task.clicked, ["TOUCHTOSTART"])


class TestChaosReconnect(unittest.TestCase):
    def test_the_interrupted_run_is_continued_not_escaped(self):
        from src.en.story_enter import handle_fork_steps
        # The live dialogue after the game was restarted mid-run.
        task = FakeTask([FakeBox("Chaos connection was lost unexpectedly. Would you like to continue?", 0.501, 0.457,
                                 width=900),
                         FakeBox("Chaos Missions", 0.352, 0.584), FakeBox("Burning Life", 0.664, 0.585),
                         FakeBox("Escape", 0.377, 0.766), FakeBox("继续", 0.642, 0.767)])
        task.frame = None
        self.assertTrue(handle_fork_steps(task))
        self.assertEqual(task.clicked, ["继续"])


class TestBackOnStoryMap(unittest.TestCase):
    LIVE = [FakeBox("故事", 0.106, 0.047), FakeBox("Chapter 3", 0.452, 0.04), FakeBox("Toward the Abyss", 0.57, 0.493),
            FakeBox("#07", 0.659, 0.491), FakeBox("Burning Life", 0.366, 0.631)]

    def test_a_handed_over_chaos_stage_hands_back_on_the_map(self):
        import tempfile
        from unittest.mock import patch
        from src.en import autostart, status
        from src.en.story_enter import handle_back_on_story_map
        with tempfile.TemporaryDirectory() as folder, patch.object(status, "PATH", Path(folder) / "s.json"):
            autostart.write_return("ChaosMode", seen=True)
            task = FakeTask([FakeBox("1563/1563", 0.212, 0.039)])
            task.name = "自动卡厄思模式"
            self.assertFalse(handle_back_on_story_map(task))
            task.all_texts = list(self.LIVE)
            self.assertTrue(handle_back_on_story_map(task))
            self.assertFalse((Path(folder) / autostart.RETURN_NAME).exists())
            self.assertIn("StoryMode", (Path(folder) / autostart.SWITCH_NAME).read_text(encoding="utf-8"))

    def test_no_hand_back_before_the_run_has_left_the_map(self):
        # Live, Act 4: the stage's panel opened over the map and the Chaos mode handed straight back.
        import tempfile
        from unittest.mock import patch
        from src.en import autostart, status
        from src.en.story_enter import handle_back_on_story_map
        with tempfile.TemporaryDirectory() as folder, patch.object(status, "PATH", Path(folder) / "s.json"):
            autostart.write_return("ChaosMode", seen=True)
            task = FakeTask(list(self.LIVE))
            task.name = "自动卡厄思模式"
            self.assertFalse(handle_back_on_story_map(task))
            self.assertTrue((Path(folder) / autostart.RETURN_NAME).exists())

    def test_nothing_without_a_hand_over(self):
        import tempfile
        from unittest.mock import patch
        from src.en import status
        from src.en.story_enter import handle_back_on_story_map
        with tempfile.TemporaryDirectory() as folder, patch.object(status, "PATH", Path(folder) / "s.json"):
            self.assertFalse(handle_back_on_story_map(FakeTask(list(self.LIVE))))


class TestStoryChaosRun(unittest.TestCase):
    def run_step(self, handed_over):
        import tempfile
        from unittest.mock import patch
        from src.en import autostart, status
        from src.en.story_enter import handle_story_chaos_run
        with tempfile.TemporaryDirectory() as folder, patch.object(status, "PATH", Path(folder) / "s.json"):
            if handed_over:
                autostart.write_return("ChaosMode", seen=True)
            task = FakeTask([FakeBox("1563/1563", 0.212, 0.039)])
            task.name, task.node_status = "自动卡厄思模式", {}
            self.assertFalse(handle_story_chaos_run(task))
            return task.node_status

    def test_a_handed_over_run_skips_the_save_target_lookup(self):
        self.assertEqual(self.run_step(handed_over=True), {"save_target_member": True})

    def test_a_chaos_run_of_its_own_still_looks_it_up(self):
        self.assertEqual(self.run_step(handed_over=False), {})


class TestChaosWalkMagnifier(unittest.TestCase):
    def test_a_handed_over_chaos_stage_looks_at_the_magnifier(self):
        import tempfile
        import cv2
        from unittest.mock import patch
        from src.en import autostart, status
        from src.en.story_enter import handle_walk_magnifier
        frame = cv2.imread(str(Path(__file__).parent / "images" / "chaos_walk_magnifier.png"))
        with tempfile.TemporaryDirectory() as folder, patch.object(status, "PATH", Path(folder) / "s.json"):
            task = FakeTask([])
            task.name, task.frame, pressed = "自动卡厄思模式", frame, []
            task.click_relative = lambda x, y: pressed.append((x, y))
            self.assertFalse(handle_walk_magnifier(task))
            autostart.write_return("ChaosMode", seen=True)
            self.assertTrue(handle_walk_magnifier(task))
        self.assertEqual(len(pressed), 1)
        self.assertAlmostEqual(pressed[0][0], 0.879, places=2)
        self.assertAlmostEqual(pressed[0][1], 0.561, places=2)


class TestLowMagnifiers(unittest.TestCase):
    def test_magnifiers_low_on_the_stage_are_found(self):
        import cv2
        from src.en.story_enter import find_magnifier
        frame = cv2.imread(str(Path(__file__).parent / "images" / "story_walk_magnifier_low.png"))
        first = find_magnifier(frame)
        self.assertAlmostEqual(first[0], 0.091, places=2)
        self.assertAlmostEqual(first[1], 0.832, places=2)
        frame[:, :300] = 0
        second = find_magnifier(frame)
        self.assertAlmostEqual(second[0], 0.755, places=1)
        self.assertGreater(second[1], 0.85)

    def test_screens_without_one_find_none(self):
        import cv2
        from src.en.story_enter import find_magnifier
        for name in ("hand_select_exhaust.png", "main.png", "effect_panel.png"):
            frame = cv2.imread(str(Path(__file__).parent / "images" / name))
            self.assertIsNone(find_magnifier(frame), name)


class TestEffectPanel(unittest.TestCase):
    LIVE = [FakeBox("Effect", 0.145, 0.05), FakeBox("Healthy", 0.686, 0.05), FakeBox("Health 1870(94.5%)", 0.82, 0.049),
            FakeBox("Chronal Ascension", 0.23, 0.236, width=250)]

    def test_the_panel_is_closed_not_read_as_speech(self):
        import cv2
        from src.en.story_enter import PANEL_CLOSE, handle_story_walk_dialogue
        # Snapshot 20261011-213818: the panel's first entry sits where a speech box's line does.
        task = FakeTask(list(self.LIVE))
        task.frame = cv2.imread(str(Path(__file__).resolve().parent / "images" / "effect_panel.png"))
        pressed = []
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertTrue(handle_story_walk_dialogue(task, NO_FIGHT))
        self.assertEqual((pressed, task.clicked), ([PANEL_CLOSE], []))


class TestChapterForward(unittest.TestCase):
    # Snapshot 20261011-214841.
    LIVE = [FakeBox("故事", 0.106, 0.047), FakeBox("Chapter 3", 0.404, 0.04), FakeBox("Epilogue", 0.178, 0.437),
            FakeBox("Epilogue l", 0.448, 0.437), FakeBox("#11", 0.274, 0.503), FakeBox("#12", 0.537, 0.502)]

    def test_a_finished_map_with_nothing_beyond_tries_the_tab_arrow(self):
        from src.en.story_enter import CHAPTER_FORWARD, handle_chapter_forward
        task = MapTask(list(self.LIVE))
        pressed = []
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertTrue(handle_chapter_forward(task))
        self.assertFalse(handle_chapter_forward(task))
        self.assertEqual(pressed, [CHAPTER_FORWARD])

    def test_a_stage_at_the_edge_is_dragged_to_instead(self):
        from src.en.story_enter import handle_chapter_forward
        task = MapTask(list(self.LIVE) + [FakeBox("#13", 0.985, 0.5, width=20)])
        self.assertFalse(handle_chapter_forward(task))


class TestStoryHub(unittest.TestCase):
    # Snapshot 20261011-220855: where backing out of finished Chapter 3 landed.
    HUB = [FakeBox("故事", 0.106, 0.047), FakeBox("Act 4 - Chapter 1, Episode 1", 0.27, 0.817, width=300),
           FakeBox("故事", 0.331, 0.773), FakeBox("Battle Missions", 0.713, 0.774, width=200),
           FakeBox("Chapter 7 B1", 0.661, 0.817, width=150)]
    # Snapshot 20261011-220628: the Battle Missions map upstream's entrance match wandered into.
    MISSIONS = [FakeBox("Battle Missions", 0.151, 0.046, width=200), FakeBox("Chapter 7", 0.403, 0.04),
                FakeBox("Battle Missions", 0.199, 0.437, width=200), FakeBox("B5", 0.276, 0.503)]

    def test_the_story_card_opens_the_next_episode(self):
        from src.en.story_enter import handle_story_hub
        task = MapTask(list(self.HUB))
        self.assertTrue(handle_story_hub(task))
        self.assertFalse(handle_story_hub(task))
        self.assertEqual(task.clicked, ["Act 4 - Chapter 1, Episode 1"])

    def test_a_story_map_is_not_the_hub(self):
        from src.en.story_enter import handle_story_hub
        self.assertFalse(handle_story_hub(MapTask(list(TestChapterForward.LIVE))))

    def test_the_battle_missions_map_is_backed_out_of_not_paged(self):
        from src.en.story_enter import CHAPTER_FORWARD, handle_chapter_forward, handle_off_story_path
        task = MapTask(list(self.MISSIONS))
        pressed = []
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertFalse(handle_chapter_forward(task))
        self.assertTrue(handle_off_story_path(task))
        self.assertEqual(pressed, [CHAPTER_FORWARD])

    def test_a_story_map_is_not_off_the_path(self):
        from src.en.story_enter import handle_off_story_path
        self.assertFalse(handle_off_story_path(MapTask(list(TestChapterForward.LIVE))))


class TestActList(unittest.TestCase):
    # Snapshot 20261011-221018.
    LIVE = [FakeBox("故事", 0.106, 0.047), FakeBox("Act 1", 0.119, 0.668), FakeBox("Act2", 0.36, 0.667),
            FakeBox("Act3", 0.595, 0.667), FakeBox("Act4N", 0.841, 0.662), FakeBox("Pilgrims of", 0.119, 0.742),
            FakeBox("Forbidden Catalyst", 0.356, 0.741), FakeBox("Seed of Karmic Fire", 0.594, 0.742),
            FakeBox("Nightmare", 0.119, 0.78), FakeBox("Through the Stars", 0.832, 0.78),
            FakeBox("A Song Rippling", 0.832, 0.742), FakeBox("Complete", 0.119, 0.841),
            FakeBox("Complete", 0.357, 0.841), FakeBox("Complete", 0.594, 0.841),
            FakeBox("Chapter 1Episode", 0.827, 0.84)]

    def test_the_first_act_not_complete_is_opened(self):
        from src.en.story_enter import handle_act_list
        task = MapTask(list(self.LIVE))
        self.assertTrue(handle_act_list(task))
        self.assertFalse(handle_act_list(task))
        self.assertEqual(task.clicked, ["Chapter 1Episode"])

    def test_every_act_complete_opens_nothing(self):
        from src.en.story_enter import handle_act_list
        boxes = [box for box in self.LIVE if box.name != "Chapter 1Episode"] + [FakeBox("Complete", 0.83, 0.841)]
        self.assertFalse(handle_act_list(MapTask(boxes)))


class TestObserveCutOff(unittest.TestCase):
    # Snapshot 20261011-222128: Act 4 Chapter 1, the chaos stage cut off on the left, #09 locked after it.
    LIVE = [FakeBox("√", 0.042, 0.045), FakeBox("故事", 0.106, 0.047), FakeBox("Chapter 1", 0.402, 0.04),
            FakeBox("米I'm back", 0.442, 0.436), FakeBox("observe", 0.027, 0.505, width=80), FakeBox("#09", 0.537, 0.502)]

    def test_the_chaos_stage_is_entered_by_what_shows_of_it(self):
        from unittest.mock import patch
        from src.en import autostart
        from src.en.story_enter import handle_chapter_forward, handle_map_drag, handle_observe_cut_off
        task = MapTask(list(self.LIVE))
        swiped, pressed, switched = [], [], []
        task.swipe_relative = lambda *args, **kwargs: swiped.append(args)
        task.click_relative = lambda x, y: pressed.append((x, y))
        self.assertFalse(handle_chapter_forward(task))
        with patch.object(autostart, "request_switch", lambda mode, then_story=False: switched.append(mode)):
            self.assertTrue(handle_observe_cut_off(task))
        self.assertEqual((task.clicked, swiped, pressed, switched), (["observe"], [], [], ["ChaosMode"]))
        task.all_texts = list(self.LIVE) + [FakeBox("#10", 0.97, 0.5, width=20)]
        self.assertFalse(handle_map_drag(task))

    def test_a_stage_at_the_right_edge_does_not_drag_away_from_a_chaos_stage(self):
        from src.en.story_enter import handle_map_drag
        task = MapTask([FakeBox("Chapter 1", 0.402, 0.04), FakeBox("Observe", 0.3, 0.505, width=80),
                        FakeBox("#02", 0.97, 0.5, width=20)])
        self.assertFalse(handle_map_drag(task))

    def test_the_chaos_stage_waits_for_a_dragged_map_to_settle(self):
        import time
        from src.en import story_enter
        task = MapTask([FakeBox("Observe", 0.3, 0.505, width=80)])
        setattr(task, story_enter.MAP_DRAG_PRESSED, time.monotonic())
        self.assertFalse(story_enter.handle_observe_stage(task))
        self.assertEqual(task.clicked, [])

    def test_a_map_without_it_is_left_alone(self):
        from src.en.story_enter import handle_observe_cut_off
        self.assertFalse(handle_observe_cut_off(MapTask(list(TestChapterForward.LIVE))))


class TestWalkChoice(unittest.TestCase):
    # Snapshot 20261011-224541: the middle card raised by the single-option press, the left phantom saying the way.
    LIVE = [FakeBox("1541/1541", 0.212, 0.038),
            FakeBox("We followed Heidemarie to the entrance of the discord. Unlike the phantom that", 0.499, 0.208,
                    width=1000),
            FakeBox("guided us here, the other phantoms interfere with the choices.", 0.5, 0.248, width=900),
            FakeBox("it's..this way...", 0.302, 0.399, width=180),
            FakeBox("Follow the phantom in the middle", 0.497, 0.737, width=380),
            FakeBox("Follow the phantom on the left", 0.229, 0.799, width=380),
            FakeBox("Event [Phantom's Guide]", 0.48, 0.777, width=300), FakeBox("Event [Phantom's Guide]", 0.219, 0.837,
                                                                                width=300),
            FakeBox("triggered", 0.425, 0.81), FakeBox("Follow the phantom on the right", 0.755, 0.798, width=380),
            FakeBox("Event [Phantom's Guide]", 0.739, 0.837, width=300), FakeBox("triggered", 0.165, 0.87),
            FakeBox("triggered", 0.686, 0.87)]
    NO_HAND = types.SimpleNamespace(_read_hand_count=lambda task: None)

    def test_the_card_a_character_points_at_is_raised(self):
        from src.en.story_enter import handle_walk_choice
        task = FakeTask(list(self.LIVE))
        self.assertTrue(handle_walk_choice(task, self.NO_HAND))
        self.assertEqual(task.clicked, ["Follow the phantom on the left"])

    def test_a_raised_card_is_taken_by_its_check_mark(self):
        from src.en.story_enter import CHOICE_TAKE_Y, handle_walk_choice
        boxes = [box for box in self.LIVE if box.name != "it's..this way..."]
        task = FakeTask(boxes)
        pressed = []
        task.click_relative = lambda x, y: pressed.append((round(x, 2), y))
        # No hint: the first card, the left one, is not the raised one, so it is raised first.
        self.assertTrue(handle_walk_choice(task, self.NO_HAND))
        self.assertEqual(task.clicked, ["Follow the phantom on the left"])
        # Then the left card raised in its place: its title above the other two, which sit level.
        raised = [FakeBox("1541/1541", 0.212, 0.038), FakeBox("Follow the phantom on the left", 0.229, 0.737, width=380),
                  FakeBox("Event [Phantom's Guide]", 0.219, 0.777, width=300),
                  FakeBox("Follow the phantom in the middle", 0.497, 0.799, width=380),
                  FakeBox("Follow the phantom on the right", 0.755, 0.798, width=380)]
        task = FakeTask(raised)
        task.click_relative = lambda x, y: pressed.append((round(x, 2), y))
        self.assertTrue(handle_walk_choice(task, self.NO_HAND))
        self.assertEqual(len(pressed), 1)
        self.assertEqual(pressed[0][1], CHOICE_TAKE_Y)
        self.assertLess(pressed[0][0], 0.35)

    def test_a_single_option_is_left_to_the_option_handler(self):
        from src.en.story_enter import handle_walk_choice
        task = FakeTask([FakeBox("1541/1541", 0.212, 0.038), FakeBox("Move on", 0.5, 0.80)])
        self.assertFalse(handle_walk_choice(task, self.NO_HAND))


class TestPilePick(unittest.TestCase):
    # Snapshot 20261011-231113: "Select up to 1 card(s) to bring to hand.", 0/1.
    LIVE = [FakeBox('Draw Pile', 0.083, 0.137),
            FakeBox('请选择1张卡牌', 0.501, 0.11),
            FakeBox('Hide', 0.916, 0.131),
            FakeBox('0/1', 0.498, 0.169),
            FakeBox('技能', 0.102, 0.297),
            FakeBox('Hovering Metal', 0.133, 0.271),
            FakeBox('Metal Pierce', 0.299, 0.27),
            FakeBox('攻击力', 0.287, 0.297),
            FakeBox('Iron Skin', 0.464, 0.269),
            FakeBox('技能', 0.457, 0.298),
            FakeBox('Prepare to Subdue', 0.668, 0.27),
            FakeBox('技能', 0.641, 0.299),
            FakeBox('Prepare to Subdue', 0.844, 0.272),
            FakeBox('Skim', 0.818, 0.298),
            FakeBox('90% Defense-Based', 0.3, 0.525),
            FakeBox('Decrease Damage Taken by', 0.478, 0.527),
            FakeBox('[ Exhaust /Finale]', 0.479, 0.506),
            FakeBox('Draw 1Attack Card(s)', 0.652, 0.498),
            FakeBox('Retain ]', 0.657, 0.474),
            FakeBox('20%for 1 turn', 0.478, 0.545),
            FakeBox('IncreaseDamage', 0.653, 0.551),
            FakeBox('of this unit', 0.656, 0.527),
            FakeBox('Draw 1Attack Card(s)', 0.829, 0.5),
            FakeBox('Retain', 0.83, 0.474),
            FakeBox('[Exhaust ]', 0.124, 0.55),
            FakeBox('Damage × 2', 0.302, 0.55),
            FakeBox('of this unit', 0.832, 0.527),
            FakeBox('3 Damage Reduction', 0.126, 0.577),
            FakeBox('5 Metallization', 0.125, 0.602),
            FakeBox('2 Metallization', 0.301, 0.602),
            FakeBox('1 Vulnerable', 0.302, 0.577),
            FakeBox('Decrease up to 4 Metallization', 0.478, 0.565),
            FakeBox('Additionally decrease Damage', 0.479, 0.586),
            FakeBox('Amount of those cards', 0.654, 0.576),
            FakeBox('Amount of those cards', 0.829, 0.575),
            FakeBox('IncreaseDamage', 0.83, 0.552),
            FakeBox('Taken by 20%for each', 0.479, 0.605),
            FakeBox('by 80% for 1turn', 0.654, 0.602),
            FakeBox('· by 80% for 1 turn', 0.831, 0.602),
            FakeBox('+Trickery Striket', 0.13, 0.728),
            FakeBox('Iceberg Cleave', 0.309, 0.73),
            FakeBox('£', 0.4, 0.704),
            FakeBox('Protect Us', 0.472, 0.729),
            FakeBox('攻击力', 0.11, 0.756),
            FakeBox('攻击力', 0.289, 0.756),
            FakeBox('技能', 0.457, 0.756),
            FakeBox('Garden of Secrets', 0.668, 0.729),
            FakeBox('强化', 0.647, 0.757),
            FakeBox('φ', 0.068, 0.793),
            FakeBox('选择', 0.939, 0.93)]

    def test_an_attack_is_picked_then_select_pressed(self):
        import time
        from src.en import story_enter
        task = FakeTask(list(self.LIVE))
        self.assertTrue(story_enter.handle_pile_pick(task))
        self.assertEqual(task.clicked, ["攻击力"])
        self.assertFalse(story_enter.handle_pile_pick(task))
        setattr(task, story_enter.PILE_PRESSED, time.monotonic() - 10)
        self.assertTrue(story_enter.handle_pile_pick(task))
        self.assertEqual(task.clicked, ["攻击力", "选择"])

    def test_select_is_pressed_when_the_counter_goes_unread_after_the_pick(self):
        import time
        from src.en import story_enter
        task = FakeTask([box for box in self.LIVE if box.name != "0/1"])
        self.assertTrue(story_enter.handle_pile_pick(task))
        setattr(task, story_enter.PILE_PRESSED, time.monotonic() - 10)
        self.assertTrue(story_enter.handle_pile_pick(task))
        self.assertEqual(task.clicked, ["攻击力", "选择"])

    def test_a_walk_is_not_the_pile(self):
        from src.en.story_enter import handle_pile_pick
        self.assertFalse(handle_pile_pick(FakeTask(list(TestWalkChoice.LIVE))))


class TestOrder(unittest.TestCase):
    def test_magnifiers_come_before_the_walk_option(self):
        from src.en import story_enter

        def named(name):
            function = lambda task: False  # noqa: E731
            function.__name__ = name
            return function

        module = types.ModuleType("utils_story")
        module.PAGE_HANDLERS = [named("handle_skip_story"), named("handle_view_event"), named("handle_confirm")]
        sys.modules["utils_story"] = module
        try:
            story_enter.place_after_magnifiers()
            story_enter.place_after_magnifiers()
        finally:
            del sys.modules["utils_story"]
        names = [handler.__name__ for handler in module.PAGE_HANDLERS]
        self.assertEqual(names, ["handle_skip_story", "handle_view_event", "handle_story_walk_dialogue",
                                 "handle_story_event_option", "handle_confirm"])


    def test_the_skip_box_is_answered_before_the_skip_button_is_pressed_again(self):
        from src.en import story_enter

        def named(name):
            function = lambda task: False  # noqa: E731
            function.__name__ = name
            return function

        story, sortie = types.ModuleType("utils_story"), types.ModuleType("utils_sortie")
        story.PAGE_HANDLERS = [named("handle_skip_story"), named("handle_auto_chat"), named("handle_confirm")]
        sortie.PAGE_HANDLERS = [named("handle_close_page"), named("handle_confirm")]
        sys.modules.update(utils_story=story, utils_sortie=sortie)
        try:
            story_enter.place_skip_confirm()
            story_enter.place_skip_confirm()
        finally:
            del sys.modules["utils_story"], sys.modules["utils_sortie"]
        self.assertEqual([handler.__name__ for handler in story.PAGE_HANDLERS],
                         ["handle_skip_dialogue_confirm", "handle_skip_story", "handle_auto_chat", "handle_confirm"])
        self.assertEqual([handler.__name__ for handler in sortie.PAGE_HANDLERS],
                         ["handle_close_page", "handle_skip_dialogue_confirm", "handle_confirm"])

if __name__ == "__main__":
    unittest.main()
