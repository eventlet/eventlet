"""
Asyncio compatibility functions.
"""
import asyncio

from greenlet import GreenletExit

from .greenthread import spawn, getcurrent
from .event import Event
from .hubs import get_hub
from .hubs.asyncio import Hub as AsyncioHub

__all__ = ["spawn_for_coroutine"]


def spawn_for_coroutine(coroutine):
    """
    Take a coroutine or some other object that can be turned into an
    ``asyncio.Future`` and turn it into a ``GreenThread``.
    """
    if not isinstance(get_hub(), AsyncioHub):
        raise RuntimeError(
            "This API only works with the asyncio hub. "
            + "Set a EVENTLET_HUB=asyncio environment variable."
        )

    def _run():
        # Convert the coroutine/Future/Task we're wrapping into a Future.
        future = asyncio.ensure_future(coroutine, loop=asyncio.get_running_loop())

        # Ensure killing the GreenThread cancels the Future:
        def _got_result(gthread):
            try:
                gthread.wait()
            except GreenletExit:
                future.cancel()

        getcurrent().link(_got_result)

        # Wait until the Future has a result.
        has_result = Event()
        future.add_done_callback(lambda _: has_result.send(True))
        has_result.wait()
        # Return the result of the Future (or raise an exception if it had an
        # exception).
        return future.result()

    # Start a GreenThread:
    return spawn(_run)
