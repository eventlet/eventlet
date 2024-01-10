"""
Asyncio compatibility functions.
"""
import asyncio
from .greenthread import spawn
from .event import Event

__all__ = ["spawn_for_coroutine"]


def spawn_for_coroutine(coroutine):
    """
    Take a coroutine or some other object that can be turned into an
    ``asyncio.Future`` and turn it into a ``GreenThread``.
    """
    # TODO error if hub is not asyncio
    def _run():
        # Convert the coroutine/Future/Task we're wrapping into a Future.
        future = asyncio.ensure_future(coroutine, loop=asyncio.get_running_loop())
        # Wait until the Future has a result.
        has_result = Event()
        future.add_done_callback(lambda _: has_result.send(True))
        has_result.wait()
        # Return the result of the Future (or raise an exception if it had an
        # exception).
        return future.result()

    # TODO what happens to Future if GreenThread is killed?
    return spawn(_run)
