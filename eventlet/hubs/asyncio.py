"""
Asyncio-based hub, originally implemented by Miguel Grinberg.
"""

# The various modules involved in asyncio need to call the original, unpatched
# standard library APIs to work: socket, select, threading, and so on. We
# therefore don't import them on the module level, since that would involve
# their imports getting patched, and instead delay importing them as much as
# possible. Then, we do a little song and dance in Hub.__init__ below so that
# when they're imported they import the original modules (select, socket, etc)
# rather than the patched ones.

import os
import sys

from eventlet.hubs import hub
from eventlet.patcher import _unmonkey_patch_asyncio_all


def is_available():
    """
    Indicate whether this hub is available, since some hubs are
    platform-specific.

    Python always has asyncio, so this is always ``True``.
    """
    return True


class Hub(hub.BaseHub):
    """An Eventlet hub implementation on top of an asyncio event loop."""

    def __init__(self):
        super().__init__()

        # Pre-emptively make sure we're using the right modules:
        _unmonkey_patch_asyncio_all()

        # The presumption is that eventlet is driving the event loop, so we
        # want a new one we control.
        import asyncio

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.sleep_event = asyncio.Event()

    def add_timer(self, timer):
        """
        Register a ``Timer``.

        Typically not called directly by users.
        """
        super().add_timer(timer)
        self.sleep_event.set()

    def _file_cb(self, cb, fileno):
        """
        Callback called by ``asyncio`` when a file descriptor has an event.
        """
        try:
            cb(fileno)
        except self.SYSTEM_EXCEPTIONS:
            raise
        except:
            self.squelch_exception(fileno, sys.exc_info())
        self.sleep_event.set()

    def add(self, evtype, fileno, cb, tb, mark_as_closed):
        """
        Add a file descriptor of given event type to the ``Hub``.  See the
        superclass for details.

        Typically not called directly by users.
        """
        try:
            os.fstat(fileno)
        except OSError:
            raise ValueError("Invalid file descriptor")
        already_listening = self.listeners[evtype].get(fileno) is not None
        listener = super().add(evtype, fileno, cb, tb, mark_as_closed)
        if not already_listening:
            if evtype == hub.READ:
                self.loop.add_reader(fileno, self._file_cb, cb, fileno)
            else:
                self.loop.add_writer(fileno, self._file_cb, cb, fileno)
        return listener

    def remove(self, listener):
        """
        Remove a listener from the ``Hub``.  See the superclass for details.

        Typically not called directly by users.
        """
        super().remove(listener)
        evtype = listener.evtype
        fileno = listener.fileno
        if not self.listeners[evtype].get(fileno):
            if evtype == hub.READ:
                self.loop.remove_reader(fileno)
            else:
                self.loop.remove_writer(fileno)

    def remove_descriptor(self, fileno):
        """
        Remove a file descriptor from the ``asyncio`` loop.

        Typically not called directly by users.
        """
        have_read = self.listeners[hub.READ].get(fileno)
        have_write = self.listeners[hub.WRITE].get(fileno)
        super().remove_descriptor(fileno)
        if have_read:
            self.loop.remove_reader(fileno)
        if have_write:
            self.loop.remove_writer(fileno)

    def run(self, *a, **kw):
        """
        Start the ``Hub`` running. See the superclass for details.
        """
        import asyncio

        async def async_run():
            if self.running:
                raise RuntimeError("Already running!")
            try:
                self.running = True
                self.stopping = False
                while not self.stopping:
                    while self.closed:
                        # We ditch all of these first.
                        self.close_one()
                    self.prepare_timers()
                    if self.debug_blocking:
                        self.block_detect_pre()
                    self.fire_timers(self.clock())
                    if self.debug_blocking:
                        self.block_detect_post()
                    self.prepare_timers()
                    wakeup_when = self.sleep_until()
                    if wakeup_when is None:
                        sleep_time = self.default_sleep()
                    else:
                        sleep_time = wakeup_when - self.clock()
                    if sleep_time > 0:
                        try:
                            await asyncio.wait_for(self.sleep_event.wait(), sleep_time)
                        except asyncio.TimeoutError:
                            pass
                        self.sleep_event.clear()
                    else:
                        await asyncio.sleep(0)
                else:
                    self.timers_canceled = 0
                    del self.timers[:]
                    del self.next_timers[:]
            finally:
                self.running = False
                self.stopping = False

        self.loop.run_until_complete(async_run())
