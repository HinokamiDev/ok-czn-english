"""Save what is on screen when a run stops moving, so a watcher can see why.

A mode that recognises nothing on a screen just waits, and the log then says nothing at all about what the screen
was - the Story mode sat silent after pressing Skip, and the only way to learn why was to ask for a screenshot. Once
the picture has not changed for a while, this writes the frame and the text OCR read off it beside the status file
and records a `takildi` event naming them, once per stuck spell.
"""

import json
import sys
import time
from collections import deque

from ok import Logger

from src.en import status

logger = Logger.get_logger(__name__)

# How long the picture has to hold still. Upstream's own fallback acts at 10s and its notice comes at 60s.
STILL_SECONDS = 25
# How long the text on screen has to stay the same. A story scene or a fight left waiting keeps its characters
# moving, so the picture never holds still there - the Story mode sat 14 minutes on one with no snapshot - while
# its text does. A dialogue playing on, or a fight on Auto, changes its text every few seconds.
TEXT_STILL_SECONDS = 45
# Mean grey-level change of the thumbnail below which two frames count as the same picture.
STILL_DIFFERENCE = 2.0
THUMBNAIL = (64, 36)
# The largest width saved, to keep each snapshot a few hundred kilobytes.
SAVED_WIDTH = 1280
FOLDER_NAME = "takilma"
# Kept for long: the captures are the test corpus every later fix is checked against.
KEEP = 300
# Held on the task.
LAST_PICTURE = "_en_snapshot_picture"
STILL_SINCE = "_en_snapshot_still_since"
REPORTED = "_en_snapshot_reported"
LAST_TEXT = "_en_snapshot_text"
TEXT_SINCE = "_en_snapshot_text_since"
TEXT_REPORTED = "_en_snapshot_text_reported"
# A question waiting for an answer is a planned wait, not a stuck screen.
ASKING = "_en_epiphany_asking"
# A watcher can ask for the current frame at any time by creating this file beside the status file. A fight can be
# stuck while its text keeps changing - OCR reads the hand differently every frame - so waiting is not always enough.
REQUEST_NAME = "goruntu.istek"
# Every click and key the run sends is noted, so a run can be caught going round in circles or doing nothing even
# while its screen and text keep moving - the two ways a stall slipped past the picture and text clocks.
ACTIONS = "_en_snapshot_actions"
LOOP_REPEATS = 8
LOOP_WITHIN = 60
IDLE_SECONDS = 180
LOOP_REPORTED = "_en_snapshot_loop_reported"
IDLE_REPORTED = "_en_snapshot_idle_reported"
RUN_SEEN = "_en_snapshot_run_seen"
LAST_CHECK = "_en_snapshot_last_check"
NEW_RUN_GAP = 60
HOOKED = "_en_snapshot_hooked"


def folder():
    return status.PATH.parent / FOLDER_NAME


def thumbnail(frame):
    """Shrink a frame to a small grey picture for comparing."""
    import cv2
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return cv2.resize(grey, THUMBNAIL, interpolation=cv2.INTER_AREA).astype("float32")


def texts_of(task):
    """List the text OCR read this frame, with where each piece sits as a share of the screen."""
    width, height = getattr(task, "width", 0) or 1, getattr(task, "height", 0) or 1
    found = []
    for box in getattr(task, "all_texts", None) or []:
        found.append({"metin": box.name,
                      "x": round((box.x + box.width / 2) / width, 3),
                      "y": round((box.y + box.height / 2) / height, 3)})
    return found


def save(task, frame, seconds):
    """Write the frame and its text, and say where they are.

    Returns:
        The image path, or None when it could not be written.
    """
    import cv2
    target = folder()
    target.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    # Two spells can end inside one second, so a taken name gets a counter rather than being overwritten.
    number = 0
    while (target / f"{stamp}.png").exists():
        number += 1
        stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{number}"
    image = target / f"{stamp}.png"
    scale = min(1.0, SAVED_WIDTH / frame.shape[1])
    small = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale))) if scale < 1 else frame
    if not cv2.imwrite(str(image), small):
        return None
    (target / f"{stamp}.json").write_text(json.dumps({
        "mod": getattr(task, "name", ""), "hareketsiz_saniye": int(seconds), "metinler": texts_of(task),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for old in sorted(target.glob("*.png"))[:-KEEP]:
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)
    return image


def text_signature(task):
    """The text on screen, as one comparable value, with digits dropped so a ticking timer is not movement."""
    return tuple(sorted({"".join(ch for ch in (box.name or "") if not ch.isdigit()).strip()
                         for box in getattr(task, "all_texts", None) or []} - {""}))


def check_text(task, now):
    """Save the frame once the text on screen has not changed for `TEXT_STILL_SECONDS`.

    Returns:
        True when a snapshot was taken.
    """
    signature = text_signature(task)
    if not signature:
        return False
    if signature != getattr(task, LAST_TEXT, None):
        setattr(task, LAST_TEXT, signature)
        setattr(task, TEXT_SINCE, now)
        setattr(task, TEXT_REPORTED, False)
        return False
    since = getattr(task, TEXT_SINCE, None)
    if since is None or getattr(task, TEXT_REPORTED, False) or now - since < TEXT_STILL_SECONDS:
        return False
    setattr(task, TEXT_REPORTED, True)
    frame = getattr(task, "frame", None)
    image = save(task, frame, now - since) if frame is not None else None
    if image:
        status.event(task, "takildi", f"Text on screen unchanged for {int(now - since)}s, snapshot {image}")
        task.log_info(f"text on screen unchanged for {int(now - since)}s, saved {image}")
    return bool(image)


def note_action(task, kind, detail):
    """Record one click or key, called from the hooks on every send."""
    actions = task.__dict__.setdefault(ACTIONS, deque(maxlen=LOOP_REPEATS * 2))
    actions.append((time.monotonic(), kind, detail))


def describe_click(args, kwargs):
    """Reduce a click's target to a coarse, comparable label."""
    target = args[0] if args else kwargs.get("x", -1)
    if hasattr(target, "x") and hasattr(target, "width"):
        return f"{getattr(target, 'name', '') or ''}@{int(target.x) // 20},{int(target.y) // 20}"
    y = args[1] if len(args) > 1 else kwargs.get("y", -1)
    try:
        return f"@{int(target) // 20},{int(y) // 20}"
    except (TypeError, ValueError):
        return "@?"


def guarded_click(original, operation, args, kwargs):
    """Send a click, and lose it rather than the run when Windows refuses to move the pointer.

    Windows refuses `SetCursorPos` while another window is in front (Burak brings Claude's window forward to watch):
    on 20 Oct the Story mode stopped mid-excursion on that error, raised from its own Confirm click. The frame after
    sees the same screen and clicks again, so a lost click only costs a frame.

    Returns:
        What the click returned, or False when it was lost.
    """
    try:
        return original(operation, *args, **kwargs)
    except Exception as error:
        if "SetCursorPos" not in str(error):
            raise
        logger.warning("click lost: the game window is not in front (SetCursorPos refused)")
        return False

def hook_actions():
    """Note every click and key a task sends. Installed once; the notes go through this module by name, so a reload
    of it changes what is noted without hooking twice."""
    try:
        from ok.task.task import ExecutorOperation
    except ImportError:
        return
    if getattr(ExecutorOperation, HOOKED, False):
        return
    original_click, original_key = ExecutorOperation.click, ExecutorOperation.send_key

    def click(self, *args, **kwargs):
        try:
            module = sys.modules[__name__]
            module.note_action(self, "click", module.describe_click(args, kwargs))
        except Exception:
            pass
        return sys.modules[__name__].guarded_click(original_click, self, args, kwargs)

    def send_key(self, key, *args, **kwargs):
        try:
            sys.modules[__name__].note_action(self, "key", str(key))
        except Exception:
            pass
        return original_key(self, key, *args, **kwargs)

    ExecutorOperation.click, ExecutorOperation.send_key = click, send_key
    setattr(ExecutorOperation, HOOKED, True)


def check_actions(task, now):
    """Save the frame when the run repeats one action over and over, or sends nothing at all for a long while.

    Returns:
        True when a snapshot was taken.
    """
    # A mode handed back to after a break starts a new run: its last action is from the previous one. Chaos, started
    # again for Act 5's second chaos stage, called itself idle for 870s on its first frame.
    previous = getattr(task, LAST_CHECK, None)
    setattr(task, LAST_CHECK, now)
    if previous is not None and now - previous > NEW_RUN_GAP:
        setattr(task, RUN_SEEN, now)
        held = getattr(task, ACTIONS, None)
        if held is not None:
            held.clear()
    actions = list(getattr(task, ACTIONS, None) or [])
    task.__dict__.setdefault(RUN_SEEN, now)
    last = actions[-1] if actions else None
    recent = actions[-LOOP_REPEATS:]
    looping = (len(recent) == LOOP_REPEATS and len({(kind, detail) for _, kind, detail in recent}) == 1
               and now - recent[0][0] <= LOOP_WITHIN)
    if not looping:
        setattr(task, LOOP_REPORTED, False)
    elif not getattr(task, LOOP_REPORTED, False):
        setattr(task, LOOP_REPORTED, True)
        return report(task, f"Same {last[1]} {last[2]} repeated {LOOP_REPEATS} times")
    quiet_since = last[0] if last else getattr(task, RUN_SEEN)
    if now - quiet_since < IDLE_SECONDS:
        setattr(task, IDLE_REPORTED, False)
        return False
    if getattr(task, IDLE_REPORTED, False):
        return False
    setattr(task, IDLE_REPORTED, True)
    return report(task, f"No click or key for {int(now - quiet_since)}s")


def report(task, reason):
    frame = getattr(task, "frame", None)
    image = save(task, frame, 0) if frame is not None else None
    if image:
        status.event(task, "takildi", f"{reason}, snapshot {image}")
        task.log_info(f"{reason.lower()}, saved {image}")
    return bool(image)


def answer_request(task):
    """Save the current frame when a watcher asked for it.

    Returns:
        True when a requested snapshot was taken.
    """
    request = status.PATH.parent / REQUEST_NAME
    if not request.exists():
        return False
    request.unlink(missing_ok=True)
    frame = getattr(task, "frame", None)
    image = save(task, frame, 0) if frame is not None else None
    if image:
        status.event(task, "takildi", f"Snapshot taken on request, {image}")
        task.log_info(f"snapshot taken on request, saved {image}")
    return bool(image)


def check(task, now=None):
    """Compare this frame with the last, and save it once it has held still long enough.

    Args:
        task: The running mode, whose `frame` is the current capture.
        now: The time, for tests.
    """
    if answer_request(task):
        return
    hook_actions()
    if getattr(task, ASKING, None):
        setattr(task, STILL_SINCE, None)
        setattr(task, TEXT_SINCE, None)
        return
    frame = getattr(task, "frame", None)
    if frame is None:
        return
    now = time.monotonic() if now is None else now
    if check_actions(task, now):
        setattr(task, REPORTED, True)
        setattr(task, TEXT_REPORTED, True)
        return
    if check_text(task, now):
        # One snapshot covers both: the picture's own clock is marked reported for this spell too.
        setattr(task, REPORTED, True)
        return
    picture = thumbnail(frame)
    last = getattr(task, LAST_PICTURE, None)
    setattr(task, LAST_PICTURE, picture)
    if last is None or float(abs(picture - last).mean()) > STILL_DIFFERENCE:
        setattr(task, STILL_SINCE, now)
        setattr(task, REPORTED, False)
        return
    since = getattr(task, STILL_SINCE, None)
    if since is None:
        since = now
    setattr(task, STILL_SINCE, since)
    if getattr(task, REPORTED, False) or now - since < STILL_SECONDS:
        return
    setattr(task, REPORTED, True)
    # The text clock is part of the same spell, so it does not report the same screen a second time.
    setattr(task, TEXT_REPORTED, True)
    image = save(task, frame, now - since)
    if image:
        status.event(task, "takildi", f"Screen unchanged for {int(now - since)}s, snapshot {image}")
        task.log_info(f"screen unchanged for {int(now - since)}s, saved {image}")


def checking(task):
    """Run `check` without letting a failure in it reach the run."""
    try:
        check(task)
    except Exception as error:
        logger.warning(f"could not take a stuck-screen snapshot: {error}")
