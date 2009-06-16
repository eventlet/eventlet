# @author Donovan Preston
# 
# Copyright (c) 2007, Linden Research, Inc.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import collections
import time

from eventlet import api


class Cancelled(RuntimeError):
    pass


class NOT_USED:
    def __repr__(self):
        return 'NOT_USED'

NOT_USED = NOT_USED()

class event(object):
    """An abstraction where an arbitrary number of coroutines
    can wait for one event from another.

    Events differ from channels in two ways:
      1) calling send() does not unschedule the current coroutine
      2) send() can only be called once; use reset() to prepare the event for
         another send()
    They are ideal for communicating return values between coroutines.

    >>> from eventlet import coros, api
    >>> evt = coros.event()
    >>> def baz(b):
    ...     evt.send(b + 1)
    ...
    >>> _ = api.spawn(baz, 3)
    >>> evt.wait()
    4
    """
    _result = None
    def __init__(self):
        self._waiters = {}
        self.reset()

    def __str__(self):
        params = (self.__class__.__name__, hex(id(self)), self._result, self._exc, len(self._waiters))
        return '<%s at %s result=%r _exc=%r _waiters[%d]>' % params

    def reset(self):
        """ Reset this event so it can be used to send again.
        Can only be called after send has been called.

        >>> from eventlet import coros
        >>> evt = coros.event()
        >>> evt.send(1)
        >>> evt.reset()
        >>> evt.send(2)
        >>> evt.wait()
        2

        Calling reset multiple times in a row is an error.

        >>> evt.reset()
        >>> evt.reset()
        Traceback (most recent call last):
        ...
        AssertionError: Trying to re-reset() a fresh event.

        """
        assert self._result is not NOT_USED, 'Trying to re-reset() a fresh event.'
        self.epoch = time.time()
        self._result = NOT_USED
        self._exc = None

    def ready(self):
        """ Return true if the wait() call will return immediately.
        Used to avoid waiting for things that might take a while to time out.
        For example, you can put a bunch of events into a list, and then visit
        them all repeatedly, calling ready() until one returns True, and then
        you can wait() on that one."""
        return self._result is not NOT_USED

    def has_exception(self):
        return self._exc is not None

    def has_result(self):
        return self._result is not NOT_USED and self._exc is None

    def poll(self, notready=None):
        if self.ready():
            return self.wait()
        return notready

    # QQQ make it return tuple (type, value, tb) instead of raising
    # because
    # 1) "poll" does not imply raising
    # 2) it's better not to screw up caller's sys.exc_info() by default
    #    (e.g. if caller wants to calls the function in except or finally)
    def poll_exception(self, notready=None):
        if self.has_exception():
            return self.wait()
        return notready

    def poll_result(self, notready=None):
        if self.has_result():
            return self.wait()
        return notready

    def wait(self):
        """Wait until another coroutine calls send.
        Returns the value the other coroutine passed to
        send.

        >>> from eventlet import coros, api
        >>> evt = coros.event()
        >>> def wait_on():
        ...    retval = evt.wait()
        ...    print "waited for", retval
        >>> _ = api.spawn(wait_on)
        >>> evt.send('result')
        >>> api.sleep(0)
        waited for result

        Returns immediately if the event has already
        occured.

        >>> evt.wait()
        'result'
        """
        if self._result is NOT_USED:
            self._waiters[api.getcurrent()] = True
            try:
                return api.get_hub().switch()
            finally:
                self._waiters.pop(api.getcurrent(), None)
        if self._exc is not None:
            api.getcurrent().throw(*self._exc)
        return self._result

    def send(self, result=None, exc=None):
        """Makes arrangements for the waiters to be woken with the
        result and then returns immediately to the parent.

        >>> from eventlet import coros, api
        >>> evt = coros.event()
        >>> def waiter():
        ...     print 'about to wait'
        ...     result = evt.wait()
        ...     print 'waited for', result
        >>> _ = api.spawn(waiter)
        >>> api.sleep(0)
        about to wait
        >>> evt.send('a')
        >>> api.sleep(0)
        waited for a

        It is an error to call send() multiple times on the same event.

        >>> evt.send('whoops')
        Traceback (most recent call last):
        ...
        AssertionError: Trying to re-send() an already-triggered event.

        Use reset() between send()s to reuse an event object.
        """
        assert self._result is NOT_USED, 'Trying to re-send() an already-triggered event.'
        self._result = result
        if exc is not None and not isinstance(exc, tuple):
            exc = (exc, )
        self._exc = exc
        hub = api.get_hub()
        if self._waiters:
            hub.schedule_call_global(0, self._do_send, self._result, self._exc, self._waiters.keys())

    def _do_send(self, result, exc, waiters):
        while waiters:
            waiter = waiters.pop()
            if waiter in self._waiters:
                if exc is None:
                    waiter.switch(result)
                else:
                    waiter.throw(*exc)

    def send_exception(self, *args):
        # the arguments and the same as for greenlet.throw
        return self.send(None, args)


class Semaphore(object):
    """An unbounded semaphore.
    Optionally initialize with a resource count, then acquire() and release()
    resources as needed. Attempting to acquire() when count is zero suspends
    the calling coroutine until count becomes nonzero again.
    """

    def __init__(self, count=0):
        self.counter  = count
        self._waiters = {}

    def __str__(self):
        params = (self.__class__.__name__, hex(id(self)), self.counter)
        return '<%s at %s counter=%r>' % params

    def locked(self):
        return self.counter <= 0

    def bounded(self):
        # for consistency with BoundedSemaphore
        return False

    def acquire(self, blocking=True):
        if not blocking and self.locked():
            return False
        while self.counter<=0:
            self._waiters[api.getcurrent()] = None
            try:
                api.get_hub().switch()
            finally:
                self._waiters.pop(api.getcurrent(), None)
        self.counter -= 1
        return True

    def __enter__(self):
        self.acquire()

    def release(self, blocking=True):
        # `blocking' parameter is for consistency with BoundedSemaphore and is ignored
        self.counter += 1
        if self._waiters:
            api.get_hub().schedule_call_global(0, self._do_acquire)
        return True

    def _do_acquire(self):
        if self._waiters and self.counter>0:
            waiter, _unused = self._waiters.popitem()
            waiter.switch()

    def __exit__(self, typ, val, tb):
        self.release()


class BoundedSemaphore(object):
    """A bounded semaphore.
    Optionally initialize with a resource count, then acquire() and release()
    resources as needed. Attempting to acquire() when count is zero suspends
    the calling coroutine until count becomes nonzero again.  Attempting to
    release() after count has reached limit suspends the calling coroutine until
    count becomes less than limit again.
    """
    def __init__(self, count, limit):
        if count > limit:
            # accidentally, this also catches the case when limit is None
            raise ValueError("'count' cannot be more than 'limit'")
        self.lower_bound = Semaphore(count)
        self.upper_bound = Semaphore(limit-count)

    def __str__(self):
        params = (self.__class__.__name__, hex(id(self)), self.lower_bound.counter, self.upper_bound.counter)
        return '<%s at %s %r/%r>' % params

    def locked(self):
        return self.lower_bound.locked()

    def bounded(self):
        return self.upper_bound.locked()

    def acquire(self, blocking=True):
        if not blocking and self.locked():
            return False
        self.upper_bound.release()
        try:
            return self.lower_bound.acquire()
        except:
            self.upper_bound.counter -= 1
            # using counter directly means that it can be less than zero.
            # however I certainly don't need to wait here and I don't seem to have
            # a need to care about such inconsistency
            raise

    def __enter__(self):
        self.acquire()

    def release(self, blocking=True):
        if not blocking and self.bounded():
            return False
        self.lower_bound.release()
        try:
            return self.upper_bound.acquire()
        except:
            self.lower_bound.counter -= 1
            raise

    def __exit__(self, typ, val, tb):
        self.release()

    @property
    def balance(self):
        return self.lower_bound.counter - self.upper_bound.counter


def semaphore(count=0, limit=None):
    if limit is None:
        return Semaphore(count)
    else:
        return BoundedSemaphore(count, limit)


class metaphore(object):
    """This is sort of an inverse semaphore: a counter that starts at 0 and
    waits only if nonzero. It's used to implement a "wait for all" scenario.

    >>> from eventlet import api, coros
    >>> count = coros.metaphore()
    >>> count.wait()
    >>> def decrementer(count, id):
    ...     print "%s decrementing" % id
    ...     count.dec()
    ...
    >>> _ = api.spawn(decrementer, count, 'A')
    >>> _ = api.spawn(decrementer, count, 'B')
    >>> count.inc(2)
    >>> count.wait()
    A decrementing
    B decrementing
    """
    def __init__(self):
        self.counter = 0
        self.event   = event()
        # send() right away, else we'd wait on the default 0 count!
        self.event.send()

    def inc(self, by=1):
        """Increment our counter. If this transitions the counter from zero to
        nonzero, make any subsequent wait() call wait.
        """
        assert by > 0
        self.counter += by
        if self.counter == by:
            # If we just incremented self.counter by 'by', and the new count
            # equals 'by', then the old value of self.counter was 0.
            # Transitioning from 0 to a nonzero value means wait() must
            # actually wait.
            self.event.reset()

    def dec(self, by=1):
        """Decrement our counter. If this transitions the counter from nonzero
        to zero, a current or subsequent wait() call need no longer wait.
        """
        assert by > 0
        self.counter -= by
        if self.counter <= 0:
            # Don't leave self.counter < 0, that will screw things up in
            # future calls.
            self.counter = 0
            # Transitioning from nonzero to 0 means wait() need no longer wait.
            self.event.send()

    def wait(self):
        """Suspend the caller only if our count is nonzero. In that case,
        resume the caller once the count decrements to zero again.
        """
        self.event.wait()

def execute(func, *args, **kw):
    """ Executes an operation asynchronously in a new coroutine, returning
    an event to retrieve the return value.

    This has the same api as the CoroutinePool.execute method; the only
    difference is that this one creates a new coroutine instead of drawing
    from a pool.

    >>> from eventlet import coros
    >>> evt = coros.execute(lambda a: ('foo', a), 1)
    >>> evt.wait()
    ('foo', 1)
    """
    evt = event()
    def _really_execute():
        evt.send(func(*args, **kw))
    api.spawn(_really_execute)
    return evt


def CoroutinePool(*args, **kwargs):
    from eventlet.pool import Pool
    return Pool(*args, **kwargs)


class queue(object):
    """Cross-coroutine queue, using semaphore to synchronize.
    The API is like a generalization of event to be able to hold more than one
    item at a time (without reset() or cancel()).

    >>> from eventlet import coros
    >>> q = coros.queue(max_size=2)
    >>> def putter(q):
    ...     q.send("first")
    ...
    >>> _ = api.spawn(putter, q)
    >>> q.ready()
    False
    >>> q.wait()
    'first'
    >>> q.ready()
    False
    >>> q.send("second")
    >>> q.ready()
    True
    >>> q.send("third")
    >>> def getter(q):
    ...     print q.wait()
    ...
    >>> _ = api.spawn(getter, q)
    >>> q.send("fourth")
    second
    """
    def __init__(self, max_size=None):
        """If you omit max_size, the queue will attempt to store an unlimited
        number of items.
        Specifying max_size means that when the queue already contains
        max_size items, an attempt to send() one more item will suspend the
        calling coroutine until someone else retrieves one.
        """
        self.items = collections.deque()
        self.sem = semaphore(count=0, limit=max_size)

    def __nonzero__(self):
        return len(self.items)>0

    def __len__(self):
        return len(self.items)

    def __str__(self):
        params = (self.__class__.__name__, hex(id(self)), self.sem, len(self.items))
        return '<%s at %s sem=%s items[%d]>' % params

    def send(self, result=None, exc=None):
        """If you send(exc=SomeExceptionClass), the corresponding wait() call
        will raise that exception.
        Otherwise, the corresponding wait() will return result (default None).
        """
        if exc is not None and not isinstance(exc, tuple):
            exc = (exc, )
        self.items.append((result, exc))
        self.sem.release()

    def send_exception(self, *args):
        # the arguments are the same as for greenlet.throw
        return self.send(exc=args)

    def wait(self):
        """Wait for an item sent by a send() call, in FIFO order.
        If the corresponding send() specifies exc=SomeExceptionClass, this
        wait() will raise that exception.
        Otherwise, this wait() will return the corresponding send() call's
        result= parameter.
        """
        self.sem.acquire()
        result, exc = self.items.popleft()
        if exc is not None:
            api.getcurrent().throw(*exc)
        return result

    def ready(self):
        # could also base this on self.sem.counter...
        return len(self.items) > 0


class Actor(object):
    """ A free-running coroutine that accepts and processes messages.

    Kind of the equivalent of an Erlang process, really.  It processes
    a queue of messages in the order that they were sent.  You must
    subclass this and implement your own version of receive().

    The actor's reference count will never drop to zero while the
    coroutine exists; if you lose all references to the actor object
    it will never be freed.
    """
    def __init__(self, concurrency = 1):
        """ Constructs an Actor, kicking off a new coroutine to process the messages.

        The concurrency argument specifies how many messages the actor will try
        to process concurrently.  If it is 1, the actor will process messages
        serially.
        """
        self._mailbox = collections.deque()
        self._event = event()
        self._killer = api.spawn(self.run_forever)
        self._pool = CoroutinePool(min_size=0, max_size=concurrency)

    def run_forever(self):
        """ Loops forever, continually checking the mailbox. """
        while True:
            if not self._mailbox:
                self._event.wait()
                self._event = event()
            else:
                # leave the message in the mailbox until after it's
                # been processed so the event doesn't get triggered
                # while in the received method
                self._pool.execute_async(
                    self.received, self._mailbox[0])
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
        ...     def received(self, (message, evt) ):
        ...         print "received", message
        ...         if evt: evt.send()
        ...
        >>> a = Greeter()

        This example uses events to synchronize between the actor and the main
        coroutine in a predictable manner, but this kinda defeats the point of
        the Actor, so don't do it in a real application.

        >>> evt = event()
        >>> a.cast( ("message 1", evt) )
        >>> evt.wait()  # force it to run at this exact moment
        received message 1
        >>> evt.reset()
        >>> a.cast( ("message 2", None) )
        >>> a.cast( ("message 3", evt) )
        >>> evt.wait()
        received message 2
        received message 3

        >>> api.kill(a._killer)   # test cleanup
        """
        raise NotImplementedError()


def _test():
    print "Running doctests.  There will be no further output if they succeed."
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    _test()
