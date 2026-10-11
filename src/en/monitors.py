"""Read the game window's geometry on a monitor left of or above the main one.

Upstream skips a window's new position and size unless they are non-negative or the game is in front, a guard meant
for minimized windows, which Windows parks at -32000. A monitor left of or above the main one is negative too, so a
game there kept a 0x0 window record, the crop slid the title bar into every frame and the bottom strip off it.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

_patched = False


def take_geometry(window, bounds, minimized):
    """Store the geometry upstream's guard turned away, the way upstream would have stored it.

    Args:
        window: The framework's `HwndWindow`, after its own update has run.
        bounds: What `get_window_bounds` reports for the window, as upstream unpacks it.
        minimized: Whether the window is minimized, which is what upstream's guard is really for.

    Returns:
        True when the record was changed.
    """
    x, y, window_width, window_height, width, height, scaling = bounds
    # Upstream took it itself: an in-front game, or a position the guard lets through.
    if minimized or window.visible or (x >= -1 and y >= -1):
        return False
    client_width, client_height = width, height
    # Upstream crops a window taller than the game's own ratio to that ratio, so a frame keeps the game's shape.
    if window.frame_aspect_ratio and height and width / height < window.frame_aspect_ratio:
        height = int(width / window.frame_aspect_ratio)
    geometry = dict(x=x, y=y, window_width=window_width, window_height=window_height, client_width=client_width,
                    client_height=client_height, width=width, height=height, scaling=scaling)
    if all(getattr(window, name) == value for name, value in geometry.items()):
        return False
    for name, value in geometry.items():
        setattr(window, name, value)
    return True


def apply():
    """Have the window record follow a game on a monitor at negative coordinates."""
    global _patched
    if _patched:
        return
    import win32gui
    from ok.device.capture_methods import hwnd_window
    from ok.device.capture_methods.hwnd_window import HwndWindow

    original = HwndWindow.do_update_window_size

    def do_update_window_size(self):
        result = original(self)
        # Upstream takes the geometry itself while the game is in front.
        if self.visible:
            return result
        try:
            if self.hwnd > 0 and win32gui.IsWindow(self.hwnd):
                bounds = hwnd_window.get_window_bounds(self.hwnd)
                if take_geometry(self, bounds, bool(win32gui.IsIconic(self.hwnd))):
                    logger.info(f"game window at ({self.x}, {self.y}) on a monitor left of or above the main one, "
                                f"window {self.window_width}x{self.window_height}, frame {self.width}x{self.height}")
        except Exception as e:
            logger.warning(f"could not read the game window's geometry: {e}")
        return result

    HwndWindow.do_update_window_size = do_update_window_size
    _patched = True
