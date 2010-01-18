from eventlet import greenthread
from eventlet import hubs

class Semaphore(object):
    """An unbounded semaphore.
    Optionally initialize with a resource *count*, then :meth:`acquire` and
    :meth:`release` resources as needed. Attempting to :meth:`acquire` when
    *count* is zero suspends the calling coroutine until *count* becomes
    nonzero again.
    """

    def __init__(self, count=0):
        self.counter  = count
        self._waiters = set()

    def __repr__(self):
        params = (self.__class__.__name__, hex(id(self)), self.counter, len(self._waiters))
        return '<%s at %s c=%s _w[%s]>' % params

    def __str__(self):
        params = (self.__class__.__name__, self.counter, len(self._waiters))
        return '<%s c=%s _w[%s]>' % params

    def locked(self):
        return self.counter <= 0

    def bounded(self):
        # for consistency with BoundedSemaphore
        return False

    def acquire(self, blocking=True):
        if not blocking and self.locked():
            return False
        if self.counter <= 0:
            self._waiters.add(greenthread.getcurrent())
            try:
                while self.counter <= 0:
                    hubs.get_hub().switch()
            finally:
                self._waiters.discard(greenthread.getcurrent())
        self.counter -= 1
        return True

    def __enter__(self):
        self.acquire()

    def release(self, blocking=True):
        # `blocking' parameter is for consistency with BoundedSemaphore and is ignored
        self.counter += 1
        if self._waiters:
            hubs.get_hub().schedule_call_global(0, self._do_acquire)
        return True

    def _do_acquire(self):
        if self._waiters and self.counter>0:
            waiter = self._waiters.pop()
            waiter.switch()

    def __exit__(self, typ, val, tb):
        self.release()

    @property
    def balance(self):
        # positive means there are free items
        # zero means there are no free items but nobody has requested one
        # negative means there are requests for items, but no items
        return self.counter - len(self._waiters)


class BoundedSemaphore(object):
    """A bounded semaphore.
    Optionally initialize with a resource *count*, then :meth:`acquire` and
    :meth:`release` resources as needed. Attempting to :meth:`acquire` when
    *count* is zero suspends the calling coroutine until count becomes nonzero
    again.  Attempting to :meth:`release` after *count* has reached *limit*
    suspends the calling coroutine until *count* becomes less than *limit*
    again.
    """
    def __init__(self, count, limit):
        if count > limit:
            # accidentally, this also catches the case when limit is None
            raise ValueError("'count' cannot be more than 'limit'")
        self.lower_bound = Semaphore(count)
        self.upper_bound = Semaphore(limit-count)

    def __repr__(self):
        params = (self.__class__.__name__, hex(id(self)), self.balance, self.lower_bound, self.upper_bound)
        return '<%s at %s b=%s l=%s u=%s>' % params

    def __str__(self):
        params = (self.__class__.__name__, self.balance, self.lower_bound, self.upper_bound)
        return '<%s b=%s l=%s u=%s>' % params

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
        return self.lower_bound.balance - self.upper_bound.balance