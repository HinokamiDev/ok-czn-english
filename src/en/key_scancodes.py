"""Send each key with its own scan code, so the game reads the key that was pressed.

ok-script's Genshin interaction posts every key with the lParam 0x1e0001, whose scan code 0x1E is the A key.
The Global client's window is GLFW (class GLFW30), and GLFW names a key from the scan code in lParam rather than
from the virtual-key code, so every hotkey reached the game as A: a card key or Enter opened and closed the Draw
Pile, and a Sortie fight sat on that screen until the stuck fallback closed it. ok-script's own PostMessage
interaction already builds the lParam from the key; this gives the Genshin one the same.
"""

import time

from ok import Logger

logger = Logger.get_logger(__name__)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
# MapVirtualKey's mode for virtual-key code to scan code.
VK_TO_VSC = 0
# Keys whose scan code needs the extended-key flag, which GLFW adds to the scan code it looks up.
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}

_patched = False


def key_lparam(vk_code, is_up, map_virtual_key):
    """Build the lParam a real key press carries.

    Args:
        vk_code: The virtual-key code.
        is_up: True for the release.
        map_virtual_key: `win32api.MapVirtualKey`, passed in so the bits can be checked without Windows.

    Returns:
        Repeat count 1, the key's scan code, the extended flag where it applies, and the release bits on key up.
    """
    lparam = (map_virtual_key(vk_code, VK_TO_VSC) & 0xFF) << 16 | 1
    if vk_code in EXTENDED:
        lparam |= 1 << 24
    if is_up:
        lparam |= (1 << 30) | (1 << 31)
    return lparam


def install(interaction_class, map_virtual_key):
    """Replace the three key senders on an interaction class.

    Args:
        interaction_class: The class to patch, normally `GenshinInteraction`.
        map_virtual_key: `win32api.MapVirtualKey`.
    """
    def do_send_key(self, key, down_time=0.02):
        vk_code = self.get_key_by_str(key)
        self.post(WM_KEYDOWN, vk_code, key_lparam(vk_code, False, map_virtual_key))
        if down_time > 0.1:
            time.sleep(down_time)
        else:
            self.post(WM_CHAR, vk_code, key_lparam(vk_code, False, map_virtual_key))
        self.post(WM_KEYUP, vk_code, key_lparam(vk_code, True, map_virtual_key))
        time.sleep(down_time if down_time <= 0.1 else 0.02)

    def do_send_key_down(self, key):
        vk_code = self.get_key_by_str(key)
        self.post(WM_KEYDOWN, vk_code, key_lparam(vk_code, False, map_virtual_key))
        self.post(WM_CHAR, vk_code, key_lparam(vk_code, False, map_virtual_key))

    def do_send_key_up(self, key):
        vk_code = self.get_key_by_str(key)
        self.post(WM_KEYUP, vk_code, key_lparam(vk_code, True, map_virtual_key))

    interaction_class.do_send_key = do_send_key
    interaction_class.do_send_key_down = do_send_key_down
    interaction_class.do_send_key_up = do_send_key_up


def apply():
    """Give the Genshin interaction real scan codes."""
    global _patched
    if _patched:
        return
    try:
        import win32api
        from ok.device.interaction_methods.genshin import GenshinInteraction
    except ImportError as error:
        logger.warning(f"could not patch key scan codes: {error}")
        return
    install(GenshinInteraction, win32api.MapVirtualKey)
    _patched = True
    logger.info("keys are sent with their own scan codes")
