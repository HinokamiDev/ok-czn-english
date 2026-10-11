"""Apply edits to the fork's own handler modules while a run is going, without restarting the app.

Every fix used to need the app closed and opened again, which also meant a UAC prompt, since the app runs elevated.
Once a frame has been handled, this looks at the modification time of the modules listed in `LIVE_MODULES` and
reloads any that changed. `importlib.reload` re-runs a module in its existing namespace, so code that looks a name up
in that module when it runs - a wrapper calling a module-level step, or a `proxy` standing in a handler list - picks
up the new definition on its next call.

What it cannot do is change how the app is wired: a module not yet imported, a handler newly added to a list, or
anything under `ok_tasks/` still needs a restart. A reload that fails leaves the previous code running and is logged.
"""

import importlib
import os
import sys
import time

from ok import Logger

logger = Logger.get_logger(__name__)

PACKAGE = "src.en"
# The modules whose handlers are written to be reloaded: wrappers that call module-level steps, list entries that are
# proxies. Reloading any other module is harmless but may not take effect until a restart.
LIVE_MODULES = ("story_enter", "story_fights", "battle_choice", "snapshot", "cards")
CHECK_EVERY = 2.0

_stamps = {}
_last_check = 0.0


def proxy(module_name, function_name):
    """Build a handler-list entry that calls a module's function by name, so a reload replaces it in place.

    Args:
        module_name: The module's import name, normally the caller's `__name__`.
        function_name: The function to call.

    Returns:
        A function carrying `function_name` as its `__name__`, which handler-list edits match on.
    """
    def calling(*args, **kwargs):
        return getattr(sys.modules[module_name], function_name)(*args, **kwargs)

    calling.__name__ = function_name
    calling.__qualname__ = function_name
    calling._en_live = (module_name, function_name)
    return calling


def loaded_stamp(module):
    """The source time the module was compiled from, read from its bytecode cache.

    Seeding the comparison from the file's current time instead missed an edit saved after the module was imported
    but before the first check ran: the new time became the baseline and the old code kept running.

    Returns:
        The source modification time recorded in the .pyc, or None when there is none to read.
    """
    import importlib.util
    try:
        cached = importlib.util.cache_from_source(module.__file__)
        with open(cached, "rb") as handle:
            header = handle.read(16)
    except (OSError, TypeError, ValueError, NotImplementedError):
        return None
    if len(header) < 16 or int.from_bytes(header[4:8], "little") != 0:
        return None
    return int.from_bytes(header[8:12], "little")


def stamp_of(module):
    try:
        return os.path.getmtime(module.__file__)
    except (OSError, AttributeError, TypeError):
        return None


def check(now=None):
    """Reload any live module whose file changed since it was last seen.

    Args:
        now: The time, for tests.

    Returns:
        The names of the modules reloaded.
    """
    global _last_check
    now = time.monotonic() if now is None else now
    if now - _last_check < CHECK_EVERY:
        return []
    _last_check = now
    reloaded = []
    for name in LIVE_MODULES:
        module = sys.modules.get(f"{PACKAGE}.{name}")
        if module is None:
            continue
        stamp = stamp_of(module)
        if stamp is None:
            continue
        if name not in _stamps:
            compiled = loaded_stamp(module)
            # A first look: the module counts as current only if its bytecode was built from this very source.
            _stamps[name] = stamp if compiled is None or compiled == int(stamp) else None
        seen = _stamps[name]
        if stamp == seen:
            continue
        _stamps[name] = stamp
        try:
            importlib.reload(module)
        except Exception as error:
            logger.error(f"could not reload {name}, the previous code keeps running: {error}", exception=error)
            continue
        reloaded.append(name)
        logger.info(f"reloaded {name} without a restart")
    return reloaded


def checking():
    """Run `check` without letting a failure in it reach the run."""
    try:
        return check()
    except Exception as error:
        logger.warning(f"could not check for edited modules: {error}")
        return []
