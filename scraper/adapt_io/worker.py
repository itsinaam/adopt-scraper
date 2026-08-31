from threading import Thread
from typing import Any, Callable


def run_in_thread(
    function: Callable[..., Any],
    *args,
    **kwargs,
) -> Any:
    result = {}
    error = {}

    def target():
        try:
            result["value"] = function(*args, **kwargs)
        except Exception as exc:
            error["exception"] = exc

    thread = Thread(target=target)
    thread.start()
    thread.join()

    if "exception" in error:
        raise error["exception"]

    return result.get("value")