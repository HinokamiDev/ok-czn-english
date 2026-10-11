"""Check that a key reaches the game as itself rather than as A.

The Global client's GLFW window names a key from the scan code in lParam, and ok-script's Genshin interaction
sent 0x1E - the A key - for every key, which turned a Sortie fight's card hotkeys into Draw Pile toggles.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.en.key_scancodes import WM_CHAR, WM_KEYDOWN, WM_KEYUP, install, key_lparam  # noqa: E402

# Set 1 scan codes for the keys a fight uses.
SCAN_CODES = {0x31: 0x02, 0x32: 0x03, 0x33: 0x04, 0x0D: 0x1C, 0x45: 0x12, 0x25: 0x4B}


def map_virtual_key(vk_code, mode):
    return SCAN_CODES[vk_code]


class FakeInteraction:
    VK = {"1": 0x31, "2": 0x32, "3": 0x33, "enter": 0x0D, "e": 0x45, "left": 0x25}

    def __init__(self):
        self.posted = []

    def get_key_by_str(self, key):
        return self.VK[key]

    def post(self, message, wparam, lparam):
        self.posted.append((message, wparam, lparam))


install(FakeInteraction, map_virtual_key)


class TestKeyScancodes(unittest.TestCase):
    def test_a_card_key_carries_its_own_scan_code(self):
        self.assertEqual(key_lparam(0x32, False, map_virtual_key) >> 16 & 0xFF, 0x03)
        self.assertNotEqual(key_lparam(0x32, False, map_virtual_key) >> 16 & 0xFF, 0x1E)

    def test_release_sets_the_previous_state_and_transition_bits(self):
        lparam = key_lparam(0x0D, True, map_virtual_key)
        self.assertEqual(lparam & 0xC0000000, 0xC0000000)
        self.assertEqual(lparam >> 16 & 0xFF, 0x1C)
        self.assertEqual(lparam & 0xFFFF, 1)

    def test_arrow_keys_are_marked_extended(self):
        self.assertTrue(key_lparam(0x25, False, map_virtual_key) & (1 << 24))
        self.assertFalse(key_lparam(0x32, False, map_virtual_key) & (1 << 24))

    def test_a_press_posts_down_char_up_with_the_keys_scan_code(self):
        interaction = FakeInteraction()
        interaction.do_send_key("enter", down_time=0)
        self.assertEqual([message for message, _, _ in interaction.posted], [WM_KEYDOWN, WM_CHAR, WM_KEYUP])
        self.assertEqual({lparam >> 16 & 0xFF for _, _, lparam in interaction.posted}, {0x1C})

    def test_down_and_up_alone_use_it_too(self):
        interaction = FakeInteraction()
        interaction.do_send_key_down("e")
        interaction.do_send_key_up("e")
        self.assertEqual({lparam >> 16 & 0xFF for _, _, lparam in interaction.posted}, {0x12})


if __name__ == "__main__":
    unittest.main()
