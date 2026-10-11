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


if __name__ == "__main__":
    unittest.main()
