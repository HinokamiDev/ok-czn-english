"""Save what is on screen when a run stops moving, so a watcher can see why.

A mode that recognises nothing on a screen just waits, and the log then says nothing at all about what the screen
was - the Story mode sat silent after pressing Skip, and the only way to learn why was to ask for a screenshot. Once
the picture has not changed for a while, this writes the frame and the text OCR read off it beside the status file
and records a `takildi` event naming them, once per stuck spell.
"""

import json
import time

from ok import Logger

from src.en import status

logger = Logger.get_logger(__name__)

# How long the picture has to hold still. Upstream's own fallback acts at 10s and its notice comes at 60s.
STILL_SECONDS = 25
# Mean grey-level change of the thumbnail below which two frames count as the same picture.
STILL_DIFFERENCE = 2.0
THUMBNAIL = (64, 36)
# The largest width saved, to keep each snapshot a few hundred kilobytes.
SAVED_WIDTH = 1280
FOLDER_NAME = "takilma"
KEEP = 20
# Held on the task.
LAST_PICTURE = "_en_snapshot_picture"
STILL_SINCE = "_en_snapshot_still_since"
REPORTED = "_en_snapshot_reported"
# A question waiting for an answer is a planned wait, not a stuck screen.
ASKING = "_en_epiphany_asking"


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


def check(task, now=None):
    """Compare this frame with the last, and save it once it has held still long enough.

    Args:
        task: The running mode, whose `frame` is the current capture.
        now: The time, for tests.
    """
    if getattr(task, ASKING, None):
        setattr(task, STILL_SINCE, None)
        return
    frame = getattr(task, "frame", None)
    if frame is None:
        return
    now = time.monotonic() if now is None else now
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
