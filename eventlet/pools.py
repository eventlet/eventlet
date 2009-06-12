# @author Donovan Preston, Aaron Brashears
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

from eventlet import api
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

    def put(self, item):
        """Put an item back into the pool, when done
        """
        if self.current_size > self.max_size:
            self.current_size -= 1
            return

        if self.channel.sem.balance < 0:
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
        if self.channel.sem.balance < 0:
            return -self.channel.sem.balance
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


if __name__=='__main__':
    import doctest
    doctest.testmod()
