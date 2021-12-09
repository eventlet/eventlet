from eventlet.semaphore import Semaphore


class Lock(Semaphore):

    """A lock.
    This is API-compatible with :class:`threading.Lock`.

    It is a context manager, and thus can be used in a with block::

      lock = Lock()
      with lock:
        do_some_stuff()
    """

    def release(self, blocking=True):
        """Modify behaviour vs :class:`Semaphore` to raise a RuntimeError
        exception if the value is greater than zero. This corrects behaviour
        to realign with :class:`threading.Lock`.
        """
        if self.counter > 0:
            raise RuntimeError("release unlocked lock")

        return super(Lock, self).release(blocking=blocking)

    def _at_fork_reinit(self):
        self.counter = 1
        self._waiters.clear()
