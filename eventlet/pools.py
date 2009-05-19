"""\
@file pools.py
@author Donovan Preston, Aaron Brashears

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
import traceback

from eventlet import api
from eventlet import channel
from eventlet import coros

class FanFailed(RuntimeError):
    pass


class SomeFailed(FanFailed):
    pass


class AllFailed(FanFailed):
    pass


class Pool(object):
    """
    When using the pool, if you do a get, you should ALWAYS do a put.
    The pattern is:

    thing = self.pool.get()
    try:
        # do stuff
    finally:
        self.pool.put(thing)

    The maximum size of the pool can be modified at runtime via the max_size attribute.
    Adjusting this number does not affect existing items checked out of the pool, nor
    on any waiters who are waiting for an item to free up.  Some indeterminate number
    of get/put cycles will be necessary before the new maximum size truly matches the
    actual operation of the pool.
    """
    def __init__(self, min_size=0, max_size=4, order_as_stack=False):
        """ Pre-populates the pool with *min_size* items.  Sets a hard limit to
        the size of the pool -- it cannot contain any more items than
        *max_size*, and if there are already *max_size* items 'checked out' of
        the pool, the pool will cause any getter to cooperatively yield until an
        item is put in.

        *order_as_stack* governs the ordering of the items in the free pool.  If
        False (the default), the free items collection (of items that were
        created and were put back in the pool) acts as a round-robin, giving
        each item approximately equal utilization.  If True, the free pool acts
        as a FILO stack, which preferentially re-uses items that have most
        recently been used.
        """
        self.min_size = min_size
        self.max_size = max_size
        self.order_as_stack = order_as_stack
        self.current_size = 0
        self.channel = channel.channel()
        self.free_items = collections.deque()
        for x in xrange(min_size):
            self.current_size += 1
            self.free_items.append(self.create())

    def get(self):
        """Return an item from the pool, when one is available
        """
        if self.free_items:
            return self.free_items.popleft()
        if self.current_size < self.max_size:
            self.current_size += 1
            return self.create()
        return self.channel.receive()

    def put(self, item):
        """Put an item back into the pool, when done
        """
        if self.current_size > self.max_size:
            self.current_size -= 1
            return

        if self.channel.balance < 0:
            self.channel.send(item)
        else:
            if self.order_as_stack:
                self.free_items.appendleft(item)
            else:
                self.free_items.append(item)

    def resize(self, new_size):
        """Resize the pool
        """
        self.max_size = new_size

    def free(self):
        """Return the number of free items in the pool.
        """
        return len(self.free_items) + self.max_size - self.current_size

    def waiting(self):
        """Return the number of routines waiting for a pool item.
        """
        if self.channel.balance < 0:
            return -self.channel.balance
        return 0

    def create(self):
        """Generate a new pool item
        """
        raise NotImplementedError("Implement in subclass")

    def fan(self, block, input_list):
        queue = coros.queue(0)
        results = []
        exceptional_results = 0
        for index, input_item in enumerate(input_list):
            pool_item = self.get()

            ## Fan out
            api.spawn(
                self._invoke, block, pool_item, input_item, index, queue)

        ## Fan back in
        for i in range(len(input_list)):
            ## Wait for all guys to send to the queue
            index, value = queue.wait()
            if isinstance(value, Exception):
                exceptional_results += 1
            results.append((index, value))

        results.sort()
        results = [value for index, value in results]

        if exceptional_results:
            if exceptional_results == len(results):
                raise AllFailed(results)
            raise SomeFailed(results)
        return results

    def _invoke(self, block, pool_item, input_item, index, queue):
        try:
            result = block(pool_item, input_item)
        except Exception, e:
            self.put(pool_item)
            queue.send((index, e))
            return
        self.put(pool_item)
        queue.send((index, result))


class Token(object):
    pass


class TokenPool(Pool):
    """A pool which gives out tokens, an object indicating that
    the person who holds the token has a right to consume some
    limited resource.
    """
    def create(self):
        return Token()


class ConnectionPool(Pool):
    """A Pool which can limit the number of concurrent http operations
    being made to a given server.

    *NOTE: *TODO:

    This does NOT currently keep sockets open. It discards the created
    http object when it is put back in the pool. This is because we do
    not yet have a combination of http clients and servers which can work
    together to do HTTP keepalive sockets without errors.
    """
    def __init__(self, proto, netloc, use_proxy, min_size=0, max_size=4):
        self.proto = proto
        self.netloc = netloc
        self.use_proxy = use_proxy
        Pool.__init__(self, min_size, max_size)

    def create(self):
        import httpc
        return httpc.make_connection(self.proto, self.netloc, self.use_proxy)

    def put(self, item):
        ## Discard item, create a new connection for the pool
        Pool.put(self, self.create())


class ExceptionWrapper(object):
    def __init__(self, e):
        self.e = e


class CoroutinePool(Pool):
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
        self.requested = coros.metaphore()
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
                sender._result = coros.NOT_USED

                sender = coros.event()
                (evt, func, args, kw) = recvd
                self._safe_apply(evt, func, args, kw)
                #api.get_hub().cancel_timers(api.getcurrent())
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
        sender = coros.event()
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
        receiver = coros.event()
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
            self._next_event = coros.event()
            return self._next_event.wait()

        result = self._tracked_events.pop(0)
        if isinstance(result, ExceptionWrapper):
            raise result.e

        if not self._tracked_events:
            self._next_event = coros.event()
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
        q = coros.queue(max_size=qsize)
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
