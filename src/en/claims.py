"""Name, in a debug run, the page handler that took each frame, so a stuck screen points at its own culprit.

Every mode runs its handlers in order and stops at the first that returns True, and several upstream handlers take a
frame without logging anything. A frozen run's log then showed the screen read every second and nothing about what
kept it. Each handler is wrapped to log its name at debug level, which a release build never writes.
"""

import functools

from ok import Logger

from src.en.handlers import each_list, register

logger = Logger.get_logger(__name__)

# Set on a wrapper, so a later task load does not wrap it again.
MARK = "_en_claim_logged"
# Parked on the task: the handler that took the last frame, so a screen held by one handler is named once.
LAST = "_en_last_claim"

_patched = False


def logging_claim(handler):
    """Wrap a page handler so it says when it takes a frame from a handler other than the last one.

    Args:
        handler: The handler as the mode's list holds it.

    Returns:
        The wrapper, carrying the handler's name and markers so the list edits still find it.
    """
    @functools.wraps(handler)
    def claimed(task):
        taken = handler(task)
        if taken and getattr(task, LAST, None) != claimed.__name__:
            setattr(task, LAST, claimed.__name__)
            logger.debug(f"frame claimed by {claimed.__name__}")
        return taken

    setattr(claimed, MARK, True)
    return claimed


def install():
    """Wrap every handler in every mode's list that is not wrapped yet."""
    for _, handlers in each_list():
        for index, handler in enumerate(handlers):
            if callable(handler) and not getattr(handler, MARK, False):
                handlers[index] = logging_claim(handler)


def apply():
    """Name the handler that takes each frame. Applied last, so it wraps what every other edit installed."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
