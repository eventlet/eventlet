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


class ExceptionWrapper(object):
    def __init__(self, e):
        self.e = e


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


class semaphore(object):
    """Classic semaphore implemented with a counter and an event.
    Optionally initialize with a resource count, then acquire() and release()
    resources as needed. Attempting to acquire() when count is zero suspends
    the calling coroutine until count becomes nonzero again.

    >>> from eventlet import coros, api
    >>> sem = coros.semaphore(2, limit=3)
    >>> sem.acquire()
    >>> sem.acquire()
    >>> def releaser(sem):
    ...     print "releasing one"
    ...     sem.release()
    ...
    >>> _ = api.spawn(releaser, sem)
    >>> sem.acquire()
    releasing one
    >>> sem.counter
    0
    >>> for x in xrange(3):
    ...     sem.release()
    ...
    >>> def acquirer(sem):
    ...     print "acquiring one"
    ...     sem.acquire()
    ...
    >>> _ = api.spawn(acquirer, sem)
    >>> sem.release()
    acquiring one
    >>> sem.counter
    3
    """
    def __init__(self, count=0, limit=None):
        if limit is not None and count > limit:
            # Prevent initializing with inconsistent values
            count = limit
        self.counter  = count
        self.limit    = limit
        self.acqevent = event()
        self.relevent = event()
        if self.counter > 0:
            # If we initially have items, then don't block acquire()s.
            self.acqevent.send()
        if self.limit is None or self.counter < self.limit:
            # If either there's no limit or we're below it, don't block on
            # release()s.
            self.relevent.send()

    def acquire(self):
        # This logic handles the self.limit is None case because None != any integer.
        while self.counter == 0:
            # Loop until there are resources to acquire. We loop because we
            # could be one of several coroutines waiting for a single item. If
            # we all get notified, only one is going to claim it, and the rest
            # of us must continue waiting.
            self.acqevent.wait()
        # claim the resource
        self.counter -= 1
        if self.counter == 0:
            # If we just transitioned from having a resource to having none,
            # make anyone else's wait() actually wait.
            self.acqevent.reset()
        if self.counter + 1 == self.limit:
            # If we just transitioned from being full to having room for one
            # more resource, notify whoever was waiting to release one.
            self.relevent.send()

    def release(self):
        # This logic handles the self.limit is None case because None != any integer.
        while self.counter == self.limit:
            self.relevent.wait()
        self.counter += 1
        if self.counter == self.limit:
            self.relevent.reset()
        if self.counter == 1:
            # If self.counter was 0 before we incremented it, then wake up
            # anybody who was waiting 
            self.acqevent.send()

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
    
    def __init__(self, min_size=0, max_size=4, track_events=False):
        self._greenlets = set()
        if track_events:
            self._tracked_events = []
            self._next_event = None
        else:
            self._tracked_events = None
        self.requested = metaphore()
        super(CoroutinePool, self).__init__(min_size, max_size)

## This doesn't yet pass its own doctest -- but I'm not even sure it's a
## wonderful idea.
##     def __del__(self):
##         """Experimental: try to prevent the calling script from exiting until
##         all coroutines in this pool have run to completion.

##         >>> from eventlet import coros
##         >>> pool = coros.CoroutinePool()
##         >>> def saw(x): print "I saw %s!"
##         ...
##         >>> pool.launch_all(saw, "GHI")
##         >>> del pool
##         I saw G!
##         I saw H!
##         I saw I!
##         """
##         self.wait_all()

    def _main_loop(self, sender):
        """ Private, infinite loop run by a pooled coroutine. """
        try:
            while True:
                recvd = sender.wait()
                # Delete the sender's result here because the very
                # first event through the loop is referenced by
                # spawn_startup, and therefore is not itself deleted.
                # This means that we have to free up its argument
                # because otherwise said argument persists in memory
                # forever.  This is generally only a problem in unit
                # tests.
                sender._result = NOT_USED
                
                sender = event()
                (evt, func, args, kw) = recvd
                self._safe_apply(evt, func, args, kw)
                api.get_hub().cancel_timers(api.getcurrent())
                # Likewise, delete these variables or else they will
                # be referenced by this frame until replaced by the
                # next recvd, which may or may not be a long time from
                # now.
                del evt, func, args, kw, recvd

                self.put(sender)
        finally:
            # if we get here, something broke badly, and all we can really
            # do is try to keep the pool from leaking items.
            # Shouldn't even try to print the exception.
            self.put(self.create())

    def _safe_apply(self, evt, func, args, kw):
        """ Private method that runs the function, catches exceptions, and
        passes back the return value in the event."""
        try:
            result = func(*args, **kw)
            if evt is not None:
                evt.send(result)
                if self._tracked_events is not None:
                    if self._next_event is None:
                        self._tracked_events.append(result)
                    else:
                        
                        ne = self._next_event
                        self._next_event = None
                        ne.send(result)
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
            if self._tracked_events is not None:
                if self._next_event is None:
                    self._tracked_events.append(ExceptionWrapper(e))
                else:
                    ne = self._next_event
                    self._next_event = None
                    ne.send(exc=e)

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

    def get(self):
        """Override of eventlet.pools.Pool interface"""
        # Track the number of requested CoroutinePool coroutines
        self.requested.inc()
        # forward call to base class
        return super(CoroutinePool, self).get()

    def put(self, item):
        """Override of eventlet.pools.Pool interface"""
        # forward call to base class
        super(CoroutinePool, self).put(item)
        # Track the number of outstanding CoroutinePool coroutines
        self.requested.dec()
        
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

    def wait(self):
        """Wait for the next execute in the pool to complete,
        and return the result.

        You must pass track_events=True to the CoroutinePool constructor
        in order to use this method.
        """
        assert self._tracked_events is not None, (
            "Must pass track_events=True to the constructor to use CoroutinePool.wait()")
        if self._next_event is not None:
            return self._next_event.wait()

        if not self._tracked_events:
            self._next_event = event()
            return self._next_event.wait()

        result = self._tracked_events.pop(0)
        if isinstance(result, ExceptionWrapper):
            raise result.e

        if not self._tracked_events:
            self._next_event = event()
        return result

    def killall(self):
        for g in self._greenlets:
            api.kill(g)

    def wait_all(self):
        """Wait until all coroutines started either by execute() or
        execute_async() have completed. If you kept the event objects returned
        by execute(), you can then call their individual wait() methods to
        retrieve results with no further actual waiting.

        >>> from eventlet import coros
        >>> pool = coros.CoroutinePool()
        >>> pool.wait_all()
        >>> def hi(name):
        ...     print "Hello, %s!" % name
        ...     return name
        ...
        >>> evt = pool.execute(hi, "world")
        >>> pool.execute_async(hi, "darkness, my old friend")
        >>> pool.wait_all()
        Hello, world!
        Hello, darkness, my old friend!
        >>> evt.wait()
        'world'
        >>> pool.wait_all()
        """
        self.requested.wait()

    def launch_all(self, function, iterable):
        """For each tuple (sequence) in iterable, launch function(*tuple) in
        its own coroutine -- like itertools.starmap(), but in parallel.
        Discard values returned by function(). You should call wait_all() to
        wait for all coroutines, newly-launched plus any previously-submitted
        execute() or execute_async() calls, to complete.

        >>> from eventlet import coros
        >>> pool = coros.CoroutinePool()
        >>> def saw(x):
        ...     print "I saw %s!" % x
        ...
        >>> pool.launch_all(saw, "ABC")
        >>> pool.wait_all()
        I saw A!
        I saw B!
        I saw C!
        """
        for tup in iterable:
            self.execute_async(function, *tup)

    def process_all(self, function, iterable):
        """For each tuple (sequence) in iterable, launch function(*tuple) in
        its own coroutine -- like itertools.starmap(), but in parallel.
        Discard values returned by function(). Don't return until all
        coroutines, newly-launched plus any previously-submitted execute() or
        execute_async() calls, have completed.

        >>> from eventlet import coros
        >>> pool = coros.CoroutinePool()
        >>> def saw(x): print "I saw %s!" % x
        ...
        >>> pool.process_all(saw, "DEF")
        I saw D!
        I saw E!
        I saw F!
        """
        self.launch_all(function, iterable)
        self.wait_all()

    def generate_results(self, function, iterable, qsize=None):
        """For each tuple (sequence) in iterable, launch function(*tuple) in
        its own coroutine -- like itertools.starmap(), but in parallel.
        Yield each of the values returned by function(), in the order they're
        completed rather than the order the coroutines were launched.

        Iteration stops when we've yielded results for each arguments tuple in
        iterable. Unlike wait_all() and process_all(), this function does not
        wait for any previously-submitted execute() or execute_async() calls.

        Results are temporarily buffered in a queue. If you pass qsize=, this
        value is used to limit the max size of the queue: an attempt to buffer
        too many results will suspend the completed CoroutinePool coroutine
        until the requesting coroutine (the caller of generate_results()) has
        retrieved one or more results by calling this generator-iterator's
        next().

        If any coroutine raises an uncaught exception, that exception will
        propagate to the requesting coroutine via the corresponding next() call.

        What I particularly want these tests to illustrate is that using this
        generator function:

        for result in generate_results(function, iterable):
            # ... do something with result ...

        executes coroutines at least as aggressively as the classic eventlet
        idiom:

        events = [pool.execute(function, *args) for args in iterable]
        for event in events:
            result = event.wait()
            # ... do something with result ...

        even without a distinct event object for every arg tuple in iterable,
        and despite the funny flow control from interleaving launches of new
        coroutines with yields of completed coroutines' results.

        (The use case that makes this function preferable to the classic idiom
        above is when the iterable, which may itself be a generator, produces
        millions of items.)

        >>> from eventlet import coros
        >>> import string
        >>> pool = coros.CoroutinePool(max_size=5)
        >>> pausers = [coros.event() for x in xrange(2)]
        >>> def longtask(evt, desc):
        ...     print "%s woke up with %s" % (desc, evt.wait())
        ... 
        >>> pool.launch_all(longtask, zip(pausers, "AB"))
        >>> def quicktask(desc):
        ...     print "returning %s" % desc
        ...     return desc
        ...
        
        (Instead of using a for loop, step through generate_results()
        items individually to illustrate timing)
        
        >>> step = iter(pool.generate_results(quicktask, string.ascii_lowercase))
        >>> print step.next()
        returning a
        returning b
        returning c
        a
        >>> print step.next()
        b
        >>> print step.next()
        c
        >>> print step.next()
        returning d
        returning e
        returning f
        d
        >>> pausers[0].send("A")
        >>> print step.next()
        e
        >>> print step.next()
        f
        >>> print step.next()
        A woke up with A
        returning g
        returning h
        returning i
        g
        >>> print "".join([step.next() for x in xrange(3)])
        returning j
        returning k
        returning l
        returning m
        hij
        >>> pausers[1].send("B")
        >>> print "".join([step.next() for x in xrange(4)])
        B woke up with B
        returning n
        returning o
        returning p
        returning q
        klmn
        """
        # Get an iterator because of our funny nested loop below. Wrap the
        # iterable in enumerate() so we count items that come through.
        tuples = iter(enumerate(iterable))
        # If the iterable is empty, this whole function is a no-op, and we can
        # save ourselves some grief by just quitting out. In particular, once
        # we enter the outer loop below, we're going to wait on the queue --
        # but if we launched no coroutines with that queue as the destination,
        # we could end up waiting a very long time.
        try:
            index, args = tuples.next()
        except StopIteration:
            return
        # From this point forward, 'args' is the current arguments tuple and
        # 'index+1' counts how many such tuples we've seen.
        # This implementation relies on the fact that _execute() accepts an
        # event-like object, and -- unless it's None -- the completed
        # coroutine calls send(result). We slyly pass a queue rather than an
        # event -- the same queue instance for all coroutines. This is why our
        # queue interface intentionally resembles the event interface.
        q = queue(max_size=qsize)
        # How many results have we yielded so far?
        finished = 0
        # This first loop is only until we've launched all the coroutines. Its
        # complexity is because if iterable contains more args tuples than the
        # size of our pool, attempting to _execute() the (poolsize+1)th
        # coroutine would suspend until something completes and send()s its
        # result to our queue. But to keep down queue overhead and to maximize
        # responsiveness to our caller, we'd rather suspend on reading the
        # queue. So we stuff the pool as full as we can, then wait for
        # something to finish, then stuff more coroutines into the pool.
        try:
            while True:
                # Before each yield, start as many new coroutines as we can fit.
                # (The self.free() test isn't 100% accurate: if we happen to be
                # executing in one of the pool's coroutines, we could _execute()
                # without waiting even if self.free() reports 0. See _execute().)
                # The point is that we don't want to wait in the _execute() call,
                # we want to wait in the q.wait() call.
                # IMPORTANT: at start, and whenever we've caught up with all
                # coroutines we've launched so far, we MUST iterate this inner
                # loop at least once, regardless of self.free() -- otherwise the
                # q.wait() call below will deadlock!
                # Recall that index is the index of the NEXT args tuple that we
                # haven't yet launched. Therefore it counts how many args tuples
                # we've launched so far.
                while self.free() > 0 or finished == index:
                    # Just like the implementation of execute_async(), save that
                    # we're passing our queue instead of None as the "event" to
                    # which to send() the result.
                    self._execute(q, function, args, {})
                    # We've consumed that args tuple, advance to next.
                    index, args = tuples.next()
                # Okay, we've filled up the pool again, yield a result -- which
                # will probably wait for a coroutine to complete. Although we do
                # have q.ready(), so we could iterate without waiting, we avoid
                # that because every yield could involve considerable real time.
                # We don't know how long it takes to return from yield, so every
                # time we do, take the opportunity to stuff more requests into the
                # pool before yielding again.
                yield q.wait()
                # Be sure to count results so we know when to stop!
                finished += 1
        except StopIteration:
            pass
        # Here we've exhausted the input iterable. index+1 is the total number
        # of coroutines we've launched. We probably haven't yielded that many
        # results yet. Wait for the rest of the results, yielding them as they
        # arrive.
        while finished < index + 1:
            yield q.wait()
            finished += 1


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

    def send(self, result=None, exc=None):
        """If you send(exc=SomeExceptionClass), the corresponding wait() call
        will raise that exception.
        Otherwise, the corresponding wait() will return result (default None).
        """
        self.items.append((result, exc))
        self.sem.release()

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
            raise exc
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
