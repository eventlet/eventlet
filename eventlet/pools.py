import collections

from eventlet import api
from eventlet import coros

__all__ = ['Pool', 'TokenPool']

# have to stick this in an exec so it works in 2.4
try:
    from contextlib import contextmanager
    exec('''
@contextmanager
def item_impl(self):
    """ Get an object out of the pool, for use with with statement. 

    >>> from eventlet import pools
    >>> pool = pools.TokenPool(max_size=4)
    >>> with pool.item() as obj:
    ...     print "got token"
    ...
    got token
    >>> pool.free()
    4
    """
    obj = self.get()
    try:
        yield obj
    finally:
        self.put(obj)
''')
except ImportError:
    item_impl = None



class Pool(object):
    """
    Pool is a base class that is meant to be subclassed.  When subclassing,
    define the :meth:`create` method to implement the desired resource.
    
    When using the pool, if you do a get, you should **always** do a
    :meth:`put`.

    The pattern is::

     thing = self.pool.get()
     try:
         thing.method()
     finally:
         self.pool.put(thing)

    The maximum size of the pool can be modified at runtime via the
    :attr:`max_size` attribute.  Adjusting this number does not affect existing
    items checked out of the pool, nor on any waiters who are waiting for an
    item to free up.  Some indeterminate number of :meth:`get`/:meth:`put`
    cycles will be necessary before the new maximum size truly matches the
    actual operation of the pool.
    """
    def __init__(self, min_size=0, max_size=4, order_as_stack=False):
        """ Pre-populates the pool with *min_size* items.  Sets a hard limit to
        the size of the pool -- it cannot contain any more items than
        *max_size*, and if there are already *max_size* items 'checked out' of
        the pool, the pool will cause any getter to cooperatively yield until an
        item is put in.

        *order_as_stack* governs the ordering of the items in the free pool.
        If ``False`` (the default), the free items collection (of items that
        were created and were put back in the pool) acts as a round-robin,
        giving each item approximately equal utilization.  If ``True``, the
        free pool acts as a FILO stack, which preferentially re-uses items that
        have most recently been used.
        """
        self.min_size = min_size
        self.max_size = max_size
        self.order_as_stack = order_as_stack
        self.current_size = 0
        self.channel = coros.queue(0)
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
            created = self.create()
            self.current_size += 1
            return created
        return self.channel.wait()

    if item_impl is not None:
        item = item_impl

    def put(self, item):
        """Put an item back into the pool, when done
        """
        if self.current_size > self.max_size:
            self.current_size -= 1
            return

        if self.waiting():
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
        return self.channel.waiting()
  
    def create(self):
        """Generate a new pool item
        """
        raise NotImplementedError("Implement in subclass")


class Token(object):
    pass


class TokenPool(Pool):
    """A pool which gives out tokens (opaque unique objects), which indicate
    that the coroutine which holds the token has a right to consume some
    limited resource.
    """
    def create(self):
        return Token()
        

