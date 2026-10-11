"""Press a Story stage's Enter button on the Global client.

Upstream's `handle_enter_stage` looks at the stage panel's button, at (0.820, 0.931), for the Chinese client's
caption "入场". The Global client captions it "Enter", which the catalog turns into "进入", so the button was never
pressed: the Story mode clicked the stage node on the map again every four seconds and the panel just stayed open.
The fork's own Enter handler only presses the round action button further right, so it never covered this one either.
"""

from ok import Logger

from src.en.handlers import loaded, register, wrap

logger = Logger.get_logger(__name__)

TAG = "Global Enter caption"
# Where upstream reads the button, and the captions that mean it.
BUTTON_POINT = (0.820, 0.931)
STAGE_CAPTION = "入场"
ENTER = "进入"

_patched = False


def pressing_enter(handle_enter_stage, utils):
    """Wrap `handle_enter_stage` so the Global client's caption counts as the button.

    Args:
        handle_enter_stage: The handler to wrap, upstream's or another patch's.
        utils: The module holding `find_box_at_point` and `_clean_match`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        box = utils.find_box_at_point(task, *BUTTON_POINT)
        if box and STAGE_CAPTION not in box.name and (utils._clean_match(box.name, ENTER) or "enter" in box.name.casefold()):
            task.log_info("stage panel's Enter button, pressing it")
            task.click_box(box)
            task.sleep(1)
            return True
        return handle_enter_stage(task)

    return wrapped


def install():
    """Wrap the Story stage handler once both modules are loaded."""
    utils, utils_story = loaded("utils"), loaded("utils_story")
    if utils is None or utils_story is None:
        return
    wrap(utils_story, "handle_enter_stage", lambda original: pressing_enter(original, utils), TAG)


def apply():
    """Let the Story mode press a stage's Enter button on the Global client."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
