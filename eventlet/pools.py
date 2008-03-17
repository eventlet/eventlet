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
import os
import socket

from eventlet import api
from eventlet import channel
from eventlet import httpc

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
    """
    def __init__(self, min_size=0, max_size=4):
        self.min_size = min_size
        self.max_size = max_size
        self.current_size = 0
        self.channel = channel.channel()
        self.free_items = collections.deque()
        for x in range(min_size):
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
        chan = channel.channel()
        results = []
        exceptional_results = 0
        for index, input_item in enumerate(input_list):
            pool_item = self.get()

            ## Fan out
            api.spawn(
                self._invoke, block, pool_item, input_item, index, chan)

        ## Fan back in
        for i in range(len(input_list)):
            ## Wait for all guys to send to the queue
            index, value = chan.receive()
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

    def _invoke(self, block, pool_item, input_item, index, chan):
        try:
            result = block(pool_item, input_item)
        except Exception, e:
            self.put(pool_item)
            chan.send((index, e))
            return
        self.put(pool_item)
        chan.send((index, result))


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
        return httpc.make_connection(self.proto, self.netloc, self.use_proxy)

    def put(self, item):
        ## Discard item, create a new connection for the pool
        Pool.put(self, self.create())
