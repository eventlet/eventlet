from eventlet import greenthread
from eventlet import hubs
from eventlet import patcher


threading = patcher.original('threading')


class Semaphore(object):
    """An unbounded semaphore.
    Optionally initialize with a resource *count*, then :meth:`acquire` and
    :meth:`release` resources as needed. Attempting to :meth:`acquire` when
    *count* is zero suspends the calling greenthread until *count* becomes
    nonzero again.

    This is API-compatible with :class:`threading.Semaphore`.

    It is a context manager, and thus can be used in a with block::

      sem = Semaphore(2)
      with sem:
        do_some_stuff()

    If not specified, *value* defaults to 1.
    """

    def __init__(self, value=1):
        self.counter  = value
        if value < 0:
            raise ValueError("Semaphore must be initialized with a positive "
                             "number, got %s" % value)
        self.total_waiters = 0
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.gt_waiters = {}
        self.thr_holders = {}


    def __repr__(self):
        params = (self.__class__.__name__, hex(id(self)),
                  self.counter, self.total_waiters)
        return '<%s at %s c=%s _w[%s]>' % params

    def __str__(self):
        params = (self.__class__.__name__, self.counter, self.total_waiters)
        return '<%s c=%s _w[%s]>' % params

    def locked(self):
        """Returns true if a call to acquire would block."""
        return self.counter <= 0

    def bounded(self):
        """Returns False; for consistency with
        :class:`~eventlet.semaphore.CappedSemaphore`."""
        return False

    def _add_greenthread_waiter_for_thread(self):
        """Add the current greenthread to list of waiters for
        the current Thread.

        Call with self.lock locked.
        """
        gt = greenthread.getcurrent()
        thr = threading.current_thread()
        wt = self.gt_waiters.setdefault(thr.ident, list())
        wt.append(gt)

    def _del_greenthread_waiter_for_thread(self):
        """Delete the current greenthread from list of waiters
        for the current Thread.

        Call with self.lock locked.
        """
        gt = greenthread.getcurrent()
        thr = threading.current_thread()
        try:
            self.gt_waiters[thr.ident].remove(gt)
            if not self.gt_waiters[thr.ident]:
                # Keep dict from growing.
                del self.gt_waiters[thr.ident]
        except (KeyError, ValueError):
            # Was removed already.
            pass

    def _get_greenthread_waiter_for_thread(self):
        """Get a waiting greenthread from the current Thread.  If
        none are waiting, return None.

        Call with self.lock locked.
        """
        thr = threading.current_thread()
        if thr.ident not in self.gt_waiters:
            return None
        waiters = self.gt_waiters[thr.ident]
        # Must be at least one entry, since our key exists in
        # the dict.
        waiter = waiters.pop(0)
        if not waiters:
            # Keep dict from growing.
            del self.gt_waiters[thr.ident]
        return waiter

    def _thread_has_greenthread_waiter(self):
        """Does this thread have a greenthread waiting?"""
        thr = threading.current_thread()
        # We remove the key from the dict if we get to 0,
        # so this works.
        return thr.ident in self.gt_waiters

    def _thread_has_hold(self):
        """Has the current Thread acquired the Semaphore already?"""
        thr = threading.current_thread()
        # We remove the key from the dict if we get to 0,
        # so this works.
        return thr.ident in self.thr_holders

    def _thread_add_holder(self):
        """Increment the number of holds the current Thread has
        on the Semaphore.
        """
        thr = threading.current_thread()
        self.thr_holders.setdefault(thr.ident, 0)
        self.thr_holders[thr.ident] += 1

    def _thread_del_holder(self):
        """Decrement the number of holds the current Thread has
        on the Semaphore.
        """
        thr = threading.current_thread()
        self.thr_holders[thr.ident] -= 1
        if not self.thr_holders[thr.ident]:
            # Keep dict from growing.
            del self.thr_holders[thr.ident]

    def _acquire(self):
        """Block until we can acquire the Semaphore.

        If the current Thread already has acquired the Semaphore,
        one of 2 things is true:

        1) Another greenthread in the current Thread is trying
           to acquire it.
        2) The current Thread is trying to acquire it again.

        If #2 is true, it's a buggy application as it's reached a
        deadlock condition.  So, we assume #1 is true and switch
        greenthreads.

        Also switch greenthreads if there are currently no holders.  An
        acquire() might be coming from another greenthread.

        Otherwise, if the current Thread does NOT have the lock, then another
        Thread must hold it.  We'll wait (using a Condition) to be
        signaled to try again.

        Call with self.lock locked.  This call can potentially unlock
        and re-lock it.
        """
        while self.locked():
            if not self.thr_holders or self._thread_has_hold():
                self._add_greenthread_waiter_for_thread()
                self.lock.release()
                try:
                    hubs.get_hub().switch()
                finally:
                    self.lock.acquire()
                    self._del_greenthread_waiter_for_thread()
            else:
                self.cond.wait()

    def acquire(self, blocking=True):
        """Acquire a semaphore.

        When invoked without arguments: if the internal counter is larger than
        zero on entry, decrement it by one and return immediately. If it is zero
        on entry, block, waiting until some other thread has called release() to
        make it larger than zero. This is done with proper interlocking so that
        if multiple acquire() calls are blocked, release() will wake exactly one
        of them up. The implementation may pick one at random, so the order in
        which blocked threads are awakened should not be relied on. There is no
        return value in this case.

        When invoked with blocking set to true, do the same thing as when called
        without arguments, and return true.

        When invoked with blocking set to false, do not block. If a call without
        an argument would block, return false immediately; otherwise, do the
        same thing as when called without arguments, and return true."""
        if not blocking and self.locked():
            return False
        if self.lock.acquire(blocking) is False:
            return False
        try:
            # Check again while locked.
            if self.locked():
                if not blocking:
                    self.lock.release()
                    return False
                self.total_waiters += 1
                try:
                    self._acquire()
                finally:
                    self.total_waiters -= 1
            self._thread_add_holder()
            self.counter -= 1
        finally:
            self.lock.release()
        return True

    def __enter__(self):
        self.acquire()

    def release(self, blocking=True):
        """Release a semaphore, incrementing the internal counter by one. When
        it was zero on entry and another thread is waiting for it to become
        larger than zero again, wake up that thread.

        The *blocking* argument is for consistency with CappedSemaphore and is
        ignored"""
        self.lock.acquire()
        try:
            try:
                self._thread_del_holder()
            except KeyError:
                pass
            self.cond.notify()
            has_waiter = self._thread_has_greenthread_waiter()
            self.counter += 1
        finally:
            self.lock.release()
        if has_waiter:
            hubs.get_hub().schedule_call_global(0, self._do_acquire)
        return True

    def _do_acquire(self):
        self.lock.acquire()
        try:
            waiter = self._get_greenthread_waiter_for_thread()
        finally:
            self.lock.release()
        if waiter:
            waiter.switch()

    def __exit__(self, typ, val, tb):
        self.release()

    @property
    def balance(self):
        """An integer value that represents how many new calls to
        :meth:`acquire` or :meth:`release` would be needed to get the counter to
        0.  If it is positive, then its value is the number of acquires that can
        happen before the next acquire would block.  If it is negative, it is
        the negative of the number of releases that would be required in order
        to make the counter 0 again (one more release would push the counter to
        1 and unblock acquirers).  It takes into account how many greenthreads
        are currently blocking in :meth:`acquire`.
        """
        # positive means there are free items
        # zero means there are no free items but nobody has requested one
        # negative means there are requests for items, but no items
        return self.counter - self.total_waiters


class BoundedSemaphore(Semaphore):
    """A bounded semaphore checks to make sure its current value doesn't exceed
    its initial value. If it does, ValueError is raised. In most situations
    semaphores are used to guard resources with limited capacity. If the
    semaphore is released too many times it's a sign of a bug. If not given,
    *value* defaults to 1."""
    def __init__(self, value=1):
        super(BoundedSemaphore, self).__init__(value)
        self.original_counter = value

    def release(self, blocking=True):
        """Release a semaphore, incrementing the internal counter by one. If
        the counter would exceed the initial value, raises ValueError.  When
        it was zero on entry and another thread is waiting for it to become
        larger than zero again, wake up that thread.

        The *blocking* argument is for consistency with :class:`CappedSemaphore`
        and is ignored"""
        self.lock.acquire()
        too_many = self.counter >= self.original_counter
        self.lock.release()
        if too_many:
            raise ValueError, "Semaphore released too many times"
        return super(BoundedSemaphore, self).release(blocking)

class CappedSemaphore(object):
    """A blockingly bounded semaphore.

    Optionally initialize with a resource *count*, then :meth:`acquire` and
    :meth:`release` resources as needed. Attempting to :meth:`acquire` when
    *count* is zero suspends the calling greenthread until count becomes nonzero
    again.  Attempting to :meth:`release` after *count* has reached *limit*
    suspends the calling greenthread until *count* becomes less than *limit*
    again.

    This has the same API as :class:`threading.Semaphore`, though its
    semantics and behavior differ subtly due to the upper limit on calls
    to :meth:`release`.  It is **not** compatible with
    :class:`threading.BoundedSemaphore` because it blocks when reaching *limit*
    instead of raising a ValueError.

    It is a context manager, and thus can be used in a with block::

      sem = CappedSemaphore(2)
      with sem:
        do_some_stuff()
    """
    def __init__(self, count, limit):
        if count < 0:
            raise ValueError("CappedSemaphore must be initialized with a "
                             "positive number, got %s" % count)
        if count > limit:
            # accidentally, this also catches the case when limit is None
            raise ValueError("'count' cannot be more than 'limit'")
        self.lower_bound = Semaphore(count)
        self.upper_bound = Semaphore(limit-count)

    def __repr__(self):
        params = (self.__class__.__name__, hex(id(self)),
                  self.balance, self.lower_bound, self.upper_bound)
        return '<%s at %s b=%s l=%s u=%s>' % params

    def __str__(self):
        params = (self.__class__.__name__, self.balance,
                  self.lower_bound, self.upper_bound)
        return '<%s b=%s l=%s u=%s>' % params

    def locked(self):
        """Returns true if a call to acquire would block."""
        return self.lower_bound.locked()

    def bounded(self):
        """Returns true if a call to release would block."""
        return self.upper_bound.locked()

    def acquire(self, blocking=True):
        """Acquire a semaphore.

        When invoked without arguments: if the internal counter is larger than
        zero on entry, decrement it by one and return immediately. If it is zero
        on entry, block, waiting until some other thread has called release() to
        make it larger than zero. This is done with proper interlocking so that
        if multiple acquire() calls are blocked, release() will wake exactly one
        of them up. The implementation may pick one at random, so the order in
        which blocked threads are awakened should not be relied on. There is no
        return value in this case.

        When invoked with blocking set to true, do the same thing as when called
        without arguments, and return true.

        When invoked with blocking set to false, do not block. If a call without
        an argument would block, return false immediately; otherwise, do the
        same thing as when called without arguments, and return true."""
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
        """Release a semaphore.  In this class, this behaves very much like
        an :meth:`acquire` but in the opposite direction.

        Imagine the docs of :meth:`acquire` here, but with every direction
        reversed.  When calling this method, it will block if the internal
        counter is greater than or equal to *limit*."""
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
        """An integer value that represents how many new calls to
        :meth:`acquire` or :meth:`release` would be needed to get the counter to
        0.  If it is positive, then its value is the number of acquires that can
        happen before the next acquire would block.  If it is negative, it is
        the negative of the number of releases that would be required in order
        to make the counter 0 again (one more release would push the counter to
        1 and unblock acquirers).  It takes into account how many greenthreads
        are currently blocking in :meth:`acquire` and :meth:`release`."""
        return self.lower_bound.balance - self.upper_bound.balance
