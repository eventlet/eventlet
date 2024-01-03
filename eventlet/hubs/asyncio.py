"""
Asyncio-based hub, originally implemented by Miguel Grinberg.
"""

import asyncio
import os

from eventlet.hubs import hub


def is_available():
    return True


class Hub(hub.BaseHub):
    """An Eventlet hub implementation on top of an asyncio event loop."""

    @staticmethod
    def is_available():
        return True

    def __init__(self):
        super().__init__()
        self.sleep_event = asyncio.Event()

    def add_timer(self, timer):
        super().add_timer(timer)
        self.sleep_event.set()

    def _file_cb(self, evtype, cb, fileno):
        def _cb():
            cb(fileno)
            self.sleep_event.set()

        loop = asyncio.get_event_loop()
        if evtype == hub.READ:
            loop.remove_reader(fileno)
        else:
            loop.remove_writer(fileno)
        self.schedule_call_global(0, cb)

    def add(self, evtype, fileno, cb, tb, mark_as_closed):
        try:
            os.fstat(fileno)
        except OSError:
            raise ValueError('Invalid file descriptor')
        already_listening = self.listeners[evtype].get(fileno) is not None
        listener = super().add(evtype, fileno, cb, tb, mark_as_closed)
        loop = asyncio.get_event_loop()
        if not already_listening:
            if evtype == hub.READ:
                loop.add_reader(fileno, self._file_cb, evtype, cb, fileno)
            else:
                loop.add_writer(fileno, self._file_cb, evtype, cb, fileno)
        return listener

    def remove(self, listener):
        super().remove(listener)
        evtype = listener.evtype
        fileno = listener.fileno
        if not self.listeners[evtype].get(fileno):
            loop = asyncio.get_event_loop()
            if evtype == hub.READ:
                loop.remove_reader(fileno)
            else:
                loop.remove_writer(fileno)

    def remove_descriptor(self, fileno):
        have_read = self.listeners[hub.READ].get(fileno)
        have_write = self.listeners[hub.WRITE].get(fileno)
        super().remove_descriptor(fileno)
        loop = asyncio.get_event_loop()
        if have_read:
            loop.remove_reader(fileno)
        if have_write:
            loop.remove_writer(fileno)

    def run(self, *a, **kw):
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
                            await asyncio.wait_for(self.sleep_event.wait(),
                                                   sleep_time)
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

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(async_run())
