"""Hand one choice to a watcher through two files, and read the answer back.

The run writes `karar-istegi.json` beside the status file, listing the options, and records a `karar` event so
`son-calisma.json` reads `karar_bekliyor`. A watcher - Burak, or an assistant reading the status file - writes
`karar.json` holding the request's id and the option number to take. Nothing here touches the game: the handler
that asked does the clicking once an answer is there, exactly as it would have clicked its own pick.
"""

import json
import os
import time
import uuid

from ok import Logger

from src.en import status

logger = Logger.get_logger(__name__)

SCHEMA = "ok-czn-hd-karar-v1"
REQUEST_NAME = "karar-istegi.json"
ANSWER_NAME = "karar.json"


def request_path():
    return status.PATH.parent / REQUEST_NAME


def answer_path():
    return status.PATH.parent / ANSWER_NAME


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def open_request(task, kind, title, options):
    """Publish a choice and wait for nobody: the caller polls `answer_for`.

    Args:
        task: The running mode, for the status event.
        kind: A short label for the kind of choice, such as "epiphany".
        title: One line saying what is being chosen.
        options: The option texts, numbered from 1 in this order.

    Returns:
        The request's id, which the answer has to repeat.
    """
    request_id = uuid.uuid4().hex[:8]
    try:
        answer_path().unlink(missing_ok=True)
        _write(request_path(), {
            "sema": SCHEMA,
            "id": request_id,
            "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tur": kind,
            "baslik": title,
            "secenekler": [{"no": number, "metin": text} for number, text in enumerate(options, start=1)],
            "cevap": {"dosya": str(answer_path()), "ornek": {"id": request_id, "secim": 1}},
        })
    except Exception as error:
        logger.warning(f"could not publish the choice: {error}")
    status.event(task, "karar", f"Waiting for a choice ({kind}, id {request_id}): {title}")
    return request_id


def answer_for(request_id, option_count):
    """Read the watcher's answer, if one has arrived for this request.

    Args:
        request_id: The id `open_request` returned.
        option_count: How many options were offered, to refuse an out-of-range answer.

    Returns:
        The chosen option's index from 0, or None while there is no valid answer.
    """
    try:
        data = json.loads(answer_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("id") != request_id:
        return None
    choice = data.get("secim")
    if isinstance(choice, int) and 1 <= choice <= option_count:
        return choice - 1
    logger.warning(f"ignoring answer {choice!r}, it is not an option number from 1 to {option_count}")
    return None


def close(task, request_id, message):
    """Clear a request once it is answered or abandoned.

    Args:
        task: The running mode, for the status event.
        request_id: The request being closed.
        message: What happened, for the status file.
    """
    for path in (request_path(), answer_path()):
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning(f"could not remove {path.name}: {error}")
    status.event(task, "karar_verildi", f"{message} (id {request_id})")
