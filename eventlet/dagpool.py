#!/usr/bin/python
"""\
@file   dagpool.py
@author Nat Goodspeed
@date   2016-08-08
@brief  Provide DAGPool class

$LicenseInfo:firstyear=2016&license=mit$
Copyright (c) 2016, Linden Research, Inc.

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
$/LicenseInfo$
"""

from eventlet.event import Event
from eventlet import greenthread

class Collision(Exception):
    """
    DAGPool raises Collision when you try to launch two greenthreads with the
    same key, or post() a result for a key corresponding to a greenthread, or
    post() twice for the same key. As with KeyError, str(collision) names the
    key in question.
    """
    pass

class DAGPool(object):
    """
    A DAGPool is a pool that constrains greenthreads, not by max concurrency,
    but by data dependencies.

    This is a way to implement general DAG dependencies. A simple dependency
    tree (flowing in either direction) can straightforwardly be implemented
    using recursion and (e.g.) GreenThread.imap(). What gets complicated is
    when a given node depends on several other nodes as well as contributing
    to several other nodes.

    With DAGPool, you concurrently launch all applicable greenthreads; each
    will proceed as soon as it has all required inputs. The DAG is implicit in
    which items are required by each greenthread.

    Each greenthread is launched in a DAGPool with a key: any value that can
    serve as a Python dict key. The caller also specifies an iterable of other
    keys on which this greenthread depends. This iterable may be empty.

    The greenthread callable must accept (key, results), where:

    key is its own key
    results is an iterable of (key, value) pairs.

    A newly-launched DAGPool greenthread is entered immediately, and can
    perform any necessary setup work. At some point it will iterate over the
    (key, value) pairs from the passed 'results' iterable. Doing so blocks the
    greenthread until a value is available for each of the keys specified in
    its initial dependencies iterable. These (key, value) pairs are delivered
    in chronological order, NOT the order in which they are initially
    specified: each value will be delivered as soon as it becomes available.

    The value returned by a DAGPool greenthread becomes the value for its
    key, which unblocks any other greenthreads waiting on that key.

    External greenthreads may also interact with a DAGPool. See wait_each(),
    waitall(), post().

    It is not recommended to constrain DAGPool producer greenthreads in a
    GreenPool: it may be hard to provably avoid deadlock.
    """

    class _Coro(object):
        """
        Internal object used to track running greenthreads
        """
        def __init__(self, greenthread, pending):
            self.greenthread = greenthread
            self.pending = pending

    def __init__(self, preload={}):
        """
        DAGPool can be prepopulated with an initial dict or iterable of (key,
        value) pairs. These (key, value) pairs are of course immediately
        available for any greenthread that depends on any of those keys.
        """
        try:
            # If a dict is passed, copy it. Don't risk a subsequent
            # modification to passed dict affecting our internal state.
            iteritems = preload.iteritems()
        except AttributeError:
            # Not a dict, just an iterable of (key, value) pairs
            iteritems = preload

        # Load the initial dict
        self.values = dict(iteritems)

        # track greenthreads
        self.coros = {}

        # The key to blocking greenthreads is the Event.
        self.event = Event()

    def wait_each(self, keys):
        """
        keys is an iterable of keys.

        wait_each(keys) is a generator producing (key, value) pairs as a value
        becomes available for each requested key. wait_each() blocks the
        calling greenthread until values become available. If the DAGPool was
        prepopulated with any values, of course those can be delivered
        immediately without waiting.

        As soon as each key acquires a value, wait_each() yields a (key,
        value) pair. Delivery order is intentionally decoupled from the
        initial sequence of keys: each value is delivered as soon as it
        becomes available. If multiple keys are available at the same time,
        wait_each() delivers each of the ready ones in arbitrary order before
        blocking again.

        The DAGPool does not distinguish between a value returned by one of
        its own greenthreads and one provided by a post() call.

        The wait_each() generator terminates (raises StopIteration) when all
        specified keys have been delivered. Thus, typical usage might be:

        for key, value in dagpool.wait_each(keys):
            # process this ready key and value
        # continue processing now that we've gotten values for all keys

        By implication, if you pass wait_each() an empty iterable of keys, it
        returns immediately without yielding anything.
        """
        # Build a local set() and then call _wait_each().
        return self._wait_each(set(keys))

    def _wait_each(self, pending):
        """
        pending is a set() of keys for which we intend to wait. THIS SET WILL
        BE DESTRUCTIVELY MODIFIED: as each key acquires a value, that key will
        be removed from the passed 'pending' set.

        In all other respects, _wait_each() behaves as described for wait_each().
        """
        while True:
            # Before even waiting, show caller any (key, value) pairs that
            # are already available. Copy 'pending' because we want to be able
            # to remove items from the original set while iterating.
            for key in pending.copy():
                try:
                    value = self.values[key]
                except KeyError:
                    pass
                else:
                    # found one, it's no longer pending
                    pending.remove(key)
                    yield (key, value)

            if not pending:
                # Once we've yielded all the caller's keys, done.
                break

            # There are still more keys pending, so wait.
            self.event.wait()

    def wait(self, keys):
        """
        keys is an iterable of keys.

        wait(keys) blocks the calling greenthread until all of those 'keys'
        have values. wait() returns a dict whose keys are the passed keys.

        wait() collects a dict whose keys are the keys, and whose values come
        from the preload data, from values returned by DAGPool greenthreads or
        from post() calls.
        """
        # This is mostly redundant with wait_each() functionality.
        return dict(self.wait_each(keys))

    def waitall(self):
        """
        waitall() blocks the calling greenthread until there is a value for
        every DAGPool greenthread launched by spawn(). It returns a dict
        containing all preload data, all data from post() and all values
        returned by spawned greenthreads.
        """
        # We don't need to wait for any coroutine that's already completed.
        # But we do need to wait for every running coroutine.
        # Discard wait()'s return value, though, because we want to return ALL
        # the values.
        self.wait(self.coros.keys())
        # As promised, return all the values.
        return self.values

    def spawn(self, key, depends, function, *args, **kwds):
        """
        Launch the passed function(key, results, ...) as a greenthread,
        passing it:

        - the specified 'key'
        - an iterable of (key, value) pairs
        - whatever other positional args or keywords you specify.

        Iterating over the 'results' iterable behaves like calling
        wait_each(depends).

        Returning from function() behaves like post(key, return_value).

        If you pass spawn() a key already passed to spawn() or post(), spawn()
        raises Collision.
        """
        if key in self.coros or key in self.values:
            raise Collision(key)

        # The order is a bit tricky. First construct the set() of keys.
        pending = set(depends)
        # It's important that we pass to _wait_each() the same 'pending' set()
        # that we store in self.coros for this key. The generator-iterator
        # returned by _wait_each() becomes the function's 'results' iterable.
        newcoro = greenthread.spawn(self._wrapper, function, key,
                                    self._wait_each(pending),
                                    *args, **kwds)
        # Also capture the same (!) set in the new _Coro object for this key.
        # We must be able to observe ready keys being removed from the set.
        self.coros[key] = self._Coro(newcoro, pending)

    def _wrapper(self, function, key, results, *args, **kwds):
        """
        This wrapper runs the top-level function in a DAGPool greenthread,
        posting its return value to the DAGPool.
        """
        try:
            # call our passed function
            result = function(key, results, *args, **kwds)
        finally:
            # function() has returned (or raised an exception). We no longer
            # need to track this greenthread in self.coros. Remove it first so
            # post() won't complain about a running greenthread.
            del self.coros[key]

        try:
            # as advertised, try to post() our return value
            self.post(key, result)
        except Collision:
            # if we've already post()ed a result, oh well
            pass

        # also, in case anyone cares...
        return result

    def spawn_many(self, depends, function, *args, **kwds):
        """
        spawn_many() accepts a single function whose parameters are the same
        as for spawn().

        The difference is that spawn_many() accepts a dependency dict. A new
        greenthread is spawned for each key in the dict. That dict key's value
        should be an iterable of other keys on which this greenthread depends.
        """
        # Iterate over a snapshot of 'depends' items
        for key, deps in depends.items():
            self.spawn(key, deps, function, *args, **kwds)

    def kill(self, key):
        """
        Kill the greenthread that was spawned with the specified 'key'.

        If no such greenthread was spawned, raise KeyError.
        """
        # let KeyError, if any, propagate
        self.coros[key].greenthread.kill()
        # once killed, remove it
        del self.coros[key]

    def post(self, key, value, replace=False):
        """
        post(key, value) stores the passed value for the passed key. It then
        causes each greenthread blocked on its results iterable, or on
        wait_each(keys), to check for new values. A waiting greenthread might
        not literally resume on every single post() of a relevant key, but the
        first post() of a relevant key ensures that it will resume eventually,
        and when it does it will catch up with all relevant post() calls.

        Calling post(key, value) when there is a running greenthread with that
        same 'key' raises Collision. If you must post(key, value) instead of
        letting the greenthread run to completion, you must first call
        kill(key).

        The DAGPool implicitly post()s the return value from each of its
        greenthreads. But a greenthread may explicitly post() a value for its
        own key, which will cause its return value to be discarded.

        Calling post(key, value, replace=False) (the default 'replace') when a
        value for that key has already been posted, by any means, raises
        Collision.

        Calling post(key, value, replace=True) when a value for that key has
        already been posted, by any means, replaces the previously-stored
        value. However, that may make it complicated to reason about the
        behavior of greenthreads waiting on that key.

        After a post(key, value1) followed by post(key, value2, replace=True),
        it is unspecified which pending wait_each([key...]) calls (or
        greenthreads iterating over 'results' involving that key) will observe
        value1 versus value2. It is guaranteed that subsequent
        wait_each([key...]) calls (or greenthreads spawned after that point)
        will observe value2.
        """
        # First, check if we're trying to post() to a key with a running
        # greenthread.
        try:
            coro = self.coros[key]
        except KeyError:
            # If there's no running greenthread with this key, carry on.
            pass
        else:
            # A DAGPool greenthread is explicitly permitted to post() to its
            # OWN key.
            if coro.greenthread is not greenthread.getcurrent():
                # oh oh, trying to post a value for running greenthread from
                # some other greenthread
                raise Collision(key)

        # Here, either we're posting a value for a key with no greenthread or
        # we're posting from that greenthread itself.

        # Has somebody already post()ed a value for this key?
        try:
            self.values[key]
        except KeyError:
            # no, we're good
            pass
        else:
            # unless replace == True, this is a problem
            if not replace:
                raise Collision(key)

        # Either we've never before posted a value for this key, or we're
        # posting with replace == True.

        # update our database
        self.values[key] = value
        # and wake up pending waiters
        self.event.send()
        # The comment in Event.reset() says: "it's better to create a new
        # event rather than reset an old one". Okay, fine. We do want to be
        # able to support new waiters, so create a new Event.
        self.event = Event()

    def __getitem__(self, key):
        """
        __getitem__(key) (aka dagpool[key]) blocks until 'key' has a value,
        then delivers that value.
        """
        # This is a degenerate case of wait_each(). Construct a list
        # containing only this 'key'. list(wait_each()) will make a list
        # containing exactly one (key, value) pair. Extract that pair, then
        # extract just its value.
        return list(self.wait_each([key]))[0][1]

    def get(self, key, default=None):
        """
        get() returns the value for 'key'. If 'key' does not yet have a value,
        get() returns 'default'.
        """
        return self.values.get(key, default)

    def keys(self):
        """
        Return the list of keys for which we currently have values. Explicitly
        return a copy rather than an iterator: don't assume our caller will
        finish iterating before new values are posted.
        """
        return self.values.keys()

    def items(self):
        """
        Return a snapshot list of currently-available (key, value) pairs.
        Don't assume our caller will finish iterating before new values are
        posted.
        """
        return self.values.items()

    def running(self):
        """
        Return number of running greenthreads. This includes greenthreads
        blocked while iterating through their 'results' iterable, that is,
        greenthreads waiting on values from other keys.
        """
        return len(self.coros)

    def running_keys(self):
        """
        Return keys for running greenthreads. This includes greenthreads
        blocked while iterating through their 'results' iterable, that is,
        greenthreads waiting on values from other keys.
        """
        # return snapshot; don't assume caller will finish iterating before we
        # next modify self.coros
        return self.coros.keys()

    def waiting(self):
        """
        Return number of waiting greenthreads, that is, greenthreads still
        waiting on values from other keys. This explicitly does NOT include
        external greenthreads waiting on wait(), waitall(), wait_each().
        """
        # n.b. if Event would provide a count of its waiters, we could say
        # something about external greenthreads as well.
        # The logic to determine this count is exactly the same as the general
        # waiting_for() call.
        return len(self.waiting_for())

    class _Omitted(object):
        pass

    # Use _Omitted instead of None as the default 'key' param so we can permit
    # None as a supported key.
    def waiting_for(self, key=_Omitted):
        """
        waiting_for(key) returns a set() of the keys for which the greenthread
        spawned with that key is still waiting. If you pass a key for which no
        greenthread was spawned, waiting_for() raises KeyError.

        waiting_for() without argument returns a dict. Its keys are the keys
        of greenthreads still waiting on one or more values. In the returned
        dict, the value of each such key is the set of other keys for which
        that greenthread is still waiting.

        This method allows diagnosing a 'hung' DAGPool. If certain
        greenthreads are making no progress, it's possible that they are
        waiting on keys for which there is no greenthread and no post() data.
        """
        # We may have greenthreads whose 'pending' entry indicates they're
        # waiting on some keys even though values have now been posted for
        # some or all of those keys, because those greenthreads have not yet
        # regained control since values were posted. So make a point of
        # excluding values that are now available.
        available = set(self.values.iterkeys())

        if key is not DAGPool._Omitted:
            # waiting_for(key) is semantically different than waiting_for().
            # It's just that they both seem to want the same method name.
            try:
                coro = self.coros[key]
            except KeyError:
                # Hmm, no running greenthread with this key. But was there
                # EVER a greenthread with this key? If not, let KeyError
                # propagate.
                self.values[key]
                # Oh good, there's a value for this key. Either the
                # greenthread finished, or somebody posted a value. Just say
                # the greenthread isn't waiting for anything.
                return set()
            else:
                # coro is the _Coro for the running greenthread with the
                # specified key.
                return coro.pending - available

        # This is a waiting_for() call, i.e. a general query rather than for a
        # specific key.

        # Start by iterating over (key, coro) pairs in self.coros. Generate
        # (key, pending) pairs in which 'pending' is the set of keys on which
        # the greenthread believes it's waiting, minus the set of keys that
        # are now available. Filter out any pair in which 'pending' is empty,
        # that is, that greenthread will be unblocked next time it resumes.
        # Make a dict from those pairs.
        return dict((key, pending)
                    for key, pending in ((key, (coro.pending - available))
                                         for key, coro in self.coros.iteritems())
                    if pending)
