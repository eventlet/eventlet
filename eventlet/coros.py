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

import collections
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


class Actor(object):
    """ A free-running coroutine that accepts and processes messages.

    Kind of the equivalent of an Erlang process, really.  It processes
    a queue of messages in the order that they were sent.  You must
    subclass this and implement your own version of receive().

    The actor's reference count will never drop to zero while the
    coroutine exists; if you lose all references to the actor object
    it will never be freed.
    """
    def __init__(self):
        """ Constructs an Actor, kicking off a new coroutine to process the messages. """
        self._mailbox = collections.deque()
        self._event = event()
        self._killer = api.spawn(self.run_forever)

    def run_forever(self):
        """ Loops forever, continually checking the mailbox. """
        while True:
            if not self._mailbox:
                self._event.wait()
                self._event.reset()
            else:
                # leave the message in the mailbox until after it's
                # been processed so the event doesn't get triggered
                # while in the received method
                self.received(self._mailbox[0])
                self._mailbox.popleft()

    def cast(self, message):
        """ Send a message to the actor.

        If the actor is busy, the message will be enqueued for later
        consumption.  There is no return value.

        >>> a = Actor()
        >>> a.received = lambda msg: msg
        >>> a.cast("hello")
        """
        self._mailbox.append(message)
        # if this is the only message, the coro could be waiting
        if len(self._mailbox) == 1:
            self._event.send()

    def received(self, message):
        """ Called to process each incoming message.

        The default implementation just raises an exception, so
        replace it with something useful!
        
        >>> class Greeter(Actor):
        ...     def received(self, message):
        ...         print "received", message
        ...
        >>> a = Greeter()
        >>> a.cast("message 1")
        >>> api.sleep(0)   # need to explicitly yield to cause the actor to run
        received message 1
        >>> a.cast("message 2")
        >>> a.cast("message 3")
        >>> api.sleep(0)
        received message 2
        received message 3
        """
        raise NotImplementedError()

def _test():
    print "Running doctests.  There will be no further output if they succeed."
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    _test()
