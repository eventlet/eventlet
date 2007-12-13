"""\
@file coros.py
@author Donovan Preston

Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import time
import traceback


from eventlet import api
from eventlet import channel
from eventlet import pools
from eventlet import greenlib

class Cancelled(RuntimeError):
    pass


NOT_USED = object()


class event(object):
    """An abstraction where an arbitrary number of coroutines
    can wait for one event from another.
    """
    _result = None
    def __init__(self):
        self.reset()

    def reset(self):
        """ Reset this event so it can be used to send again.
        Can only be called after send has been called."""
        assert self._result is not NOT_USED
        self.epoch = time.time()
        self._result = NOT_USED
        self._waiters = {}

    def wait(self):
        """wait until another coroutine calls send.
        Returns the value the other coroutine passed to
        send. Returns immediately if the event has already
        occured.
        """
        if self._result is NOT_USED:
            self._waiters[api.getcurrent()] = True
            return api.get_hub().switch()
        if self._exc is not None:
            raise self._exc
        return self._result

    def cancel(self, waiter):
        """Raise an exception into a coroutine which called
        wait() an this event instead of returning a value
        from wait. Sends the eventlet.coros.Cancelled
        exception

        waiter: The greenlet (greenlet.getcurrent()) of the 
            coroutine to cancel
        """
        if waiter in self._waiters:
            del self._waiters[waiter]
            api.get_hub().schedule_call(
                0, greenlib.switch, waiter, None, Cancelled())

    def send(self, result=None, exc=None):
        """Resume all previous and further
        calls to wait() with result.
        """
        assert self._result is NOT_USED
        self._result = result
        self._exc = exc
        hub = api.get_hub()
        for waiter in self._waiters:
            hub.schedule_call(0, greenlib.switch, waiter, self._result)


def execute(func, *args, **kw):
    evt = event()
    def _really_execute():
        evt.send(func(*args, **kw))
    api.spawn(_really_execute)
    return evt


class CoroutinePool(pools.Pool):
    """ Like a thread pool, but with coroutines. """
    def _main_loop(self, sender):
        while True:
            recvd = sender.wait()
            sender.reset()
            (evt, func, args, kw) = recvd
            try:
                result = func(*args, **kw)
                if evt is not None:
                    evt.send(result)
            except api.GreenletExit:
                pass
            except Exception, e:
                traceback.print_exc()
                if evt is not None:
                    evt.send(exc=e)
            api.get_hub().runloop.cancel_timers(api.getcurrent())
            self.put(sender)

    def create(self):
        """Private implementation of eventlet.pools.Pool
        interface. Creates an event and spawns the
        _main_loop coroutine, passing the event.
        The event is used to send a callable into the
        new coroutine, to be executed.
        """
        sender = event()
        api.spawn(self._main_loop, sender)
        return sender

    def execute(self, func, *args, **kw):
        """Execute func in one of the coroutines maintained
        by the pool, when one is free.

        Immediately returns an eventlet.coros.event object which
        func's result will be sent to when it is available.
        """
        sender = self.get()
        receiver = event()
        sender.send((receiver, func, args, kw))
        return receiver

    def execute_async(self, func, *args, **kw):
        """Execute func in one of the coroutines maintained
        by the pool, when one is free.

        This version does not provide the return value.
        """
        sender = self.get()
        sender.send((None, func, args, kw))


class pipe(object):
    """ Implementation of pipe using events.  Not tested!  Not used, either."""
    def __init__(self):
        self._event = event()
        self._buffer = ''

    def send(self, txt):
        self._buffer += txt
        evt, self._event = self._event, event()
        evt.send()

    def recv(self, num=16384):
        if not self._buffer:
            self._event.wait()
        if num >= len(self._buffer):
            buf, self._buffer = self._buffer, ''
        else:
            buf, self._buffer = self._buffer[:num], self._buffer[num:]
        return buf

