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
import sys
import time
import traceback


from eventlet import api
from eventlet import channel
from eventlet import pools
from eventlet import greenlib


try:
    set
except NameError:  # python 2.3 compatibility
    from sets import Set as set


class Cancelled(RuntimeError):
    pass


NOT_USED = object()


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
        self.reset()

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
        self._waiters = {}
        
    def ready(self):
        """ Return true if the wait() call will return immediately. 
        Used to avoid waiting for things that might take a while to time out.
        For example, you can put a bunch of events into a list, and then visit
        them all repeatedly, calling ready() until one returns True, and then
        you can wait() on that one."""
        return self._result is not NOT_USED

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
            
        >>> from eventlet import coros, api
        >>> evt = coros.event()
        >>> def wait_on():
        ...    try:
        ...        print "received " + evt.wait()
        ...    except coros.Cancelled, c:
        ...        print "Cancelled"
        ...
        >>> waiter = api.spawn(wait_on)
                
        The cancel call works on coroutines that are in the wait() call.
        
        >>> api.sleep(0)  # enter the wait()
        >>> evt.cancel(waiter)
        >>> api.sleep(0)  # receive the exception
        Cancelled
        
        The cancel is invisible to coroutines that call wait() after cancel()
        is called.  This is different from send()'s behavior, where the result
        is passed to any waiter regardless of the ordering of the calls.
        
        >>> waiter = api.spawn(wait_on)
        >>> api.sleep(0)
        
        Cancels have no effect on the ability to send() to the event.
        
        >>> evt.send('stuff')
        >>> api.sleep(0)
        received stuff
        """
        if waiter in self._waiters:
            del self._waiters[waiter]
            api.get_hub().schedule_call(
                0, greenlib.switch, waiter, None, Cancelled())

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
        self._exc = exc
        hub = api.get_hub()
        for waiter in self._waiters:
            hub.schedule_call(0, greenlib.switch, waiter, self._result)


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


class CoroutinePool(pools.Pool):
    """ Like a thread pool, but with coroutines. 
    
    Coroutine pools are useful for splitting up tasks or globally controlling
    concurrency.  You don't retrieve the coroutines directly with get() -- 
    instead use the execute() and execute_async() methods to run code.
    
    >>> from eventlet import coros, api
    >>> p = coros.CoroutinePool(max_size=2)
    >>> def foo(a):
    ...   print "foo", a
    ... 
    >>> evt = p.execute(foo, 1)
    >>> evt.wait()
    foo 1
    
    Once the pool is exhausted, calling an execute forces a yield.
    
    >>> p.execute_async(foo, 2)
    >>> p.execute_async(foo, 3)
    >>> p.free()
    0
    >>> p.execute_async(foo, 4)
    foo 2
    foo 3
    
    >>> api.sleep(0)
    foo 4
    """
    
    def __init__(self, min_size=0, max_size=4):
        self._greenlets = set()
        super(CoroutinePool, self).__init__(min_size, max_size)
    
    def _main_loop(self, sender):
        """ Private, infinite loop run by a pooled coroutine. """
        try:
            while True:
                recvd = sender.wait()
                sender = event()
                (evt, func, args, kw) = recvd
                self._safe_apply(evt, func, args, kw)
                api.get_hub().runloop.cancel_timers(api.getcurrent())
                self.put(sender)
        finally:
            # if we get here, something broke badly, and all we can really
            # do is try to keep the pool from leaking items
            self.put(self.create())
            
    def _safe_apply(self, evt, func, args, kw):
        """ Private method that runs the function, catches exceptions, and
        passes back the return value in the event."""
        try:
            result = func(*args, **kw)
            if evt is not None:
                evt.send(result)
        except api.GreenletExit, e:
            # we're printing this out to see if it ever happens
            # in practice
            print "GreenletExit raised in coroutine pool", e
            if evt is not None:
                evt.send(e)  # sent as a return value, not an exception
        except KeyboardInterrupt:
            raise  # allow program to exit
        except Exception, e:
            traceback.print_exc()
            if evt is not None:
                evt.send(exc=e)
                
    def _execute(self, evt, func, args, kw):
        """ Private implementation of the execute methods.
        """
        # if reentering an empty pool, don't try to wait on a coroutine freeing 
        # itself -- instead, just execute in the current coroutine
        if self.free() == 0 and api.getcurrent() in self._greenlets:
            self._safe_apply(evt, func, args, kw)
        else:
            sender = self.get()
            sender.send((evt, func, args, kw))

    def create(self):
        """Private implementation of eventlet.pools.Pool
        interface. Creates an event and spawns the
        _main_loop coroutine, passing the event.
        The event is used to send a callable into the
        new coroutine, to be executed.
        """
        sender = event()
        self._greenlets.add(api.spawn(self._main_loop, sender))
        return sender
        
    def execute(self, func, *args, **kw):
        """Execute func in one of the coroutines maintained
        by the pool, when one is free.

        Immediately returns an eventlet.coros.event object which
        func's result will be sent to when it is available.
        
        >>> from eventlet import coros
        >>> p = coros.CoroutinePool()
        >>> evt = p.execute(lambda a: ('foo', a), 1)
        >>> evt.wait()
        ('foo', 1)
        """
        receiver = event()
        self._execute(receiver, func, args, kw)
        return receiver

    def execute_async(self, func, *args, **kw):
        """Execute func in one of the coroutines maintained
        by the pool, when one is free.

        No return value is provided.
        >>> from eventlet import coros, api
        >>> p = coros.CoroutinePool()
        >>> def foo(a):
        ...   print "foo", a
        ... 
        >>> p.execute_async(foo, 1)
        >>> api.sleep(0)
        foo 1
        """
        self._execute(None, func, args, kw)


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
