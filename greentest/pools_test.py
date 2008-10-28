"""\
@file test_pools.py
@author Donovan Preston, Aaron Brashears

Copyright (c) 2006-2007, Linden Research, Inc.
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

import unittest

from eventlet import api
from eventlet import channel
from eventlet import pools


class IntPool(pools.Pool):
    def create(self):
        self.current_integer = getattr(self, 'current_integer', 0) + 1
        return self.current_integer


class TestIntPool(unittest.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = IntPool(min_size=0, max_size=4)

    def test_integers(self):
        # Do not actually use this pattern in your code. The pool will be
        # exhausted, and unrestoreable.
        # If you do a get, you should ALWAYS do a put, probably like this:
        # try:
        #     thing = self.pool.get()
        #     # do stuff
        # finally:
        #     self.pool.put(thing)

        # with self.pool.some_api_name() as thing:
        #     # do stuff
        self.assertEquals(self.pool.get(), 1)
        self.assertEquals(self.pool.get(), 2)
        self.assertEquals(self.pool.get(), 3)
        self.assertEquals(self.pool.get(), 4)

    def test_free(self):
        self.assertEquals(self.pool.free(), 4)
        gotten = self.pool.get()
        self.assertEquals(self.pool.free(), 3)
        self.pool.put(gotten)
        self.assertEquals(self.pool.free(), 4)

    def test_exhaustion(self):
        waiter = channel.channel()
        def consumer():
            gotten = None
            try:
                gotten = self.pool.get()
            finally:
                waiter.send(gotten)

        api.spawn(consumer)

        one, two, three, four = (
            self.pool.get(), self.pool.get(), self.pool.get(), self.pool.get())
        self.assertEquals(self.pool.free(), 0)

        # Let consumer run; nothing will be in the pool, so he will wait
        api.sleep(0)

        # Wake consumer
        self.pool.put(one)

        # wait for the consumer
        self.assertEquals(waiter.receive(), one)

    def test_blocks_on_pool(self):
        waiter = channel.channel()
        def greedy():
            self.pool.get()
            self.pool.get()
            self.pool.get()
            self.pool.get()
            # No one should be waiting yet.
            self.assertEquals(self.pool.waiting(), 0)
            # The call to the next get will unschedule this routine.
            self.pool.get()
            # So this send should never be called.
            waiter.send('Failed!')

        killable = api.spawn(greedy)

        # no one should be waiting yet.
        self.assertEquals(self.pool.waiting(), 0)

        ## Wait for greedy
        api.sleep(0)

        ## Greedy should be blocking on the last get
        self.assertEquals(self.pool.waiting(), 1)

        ## Send will never be called, so balance should be 0.
        self.assertEquals(waiter.balance, 0)

        api.kill(killable)


class TestAbstract(unittest.TestCase):
    mode = 'static'
    def test_abstract(self):
        ## Going for 100% coverage here
        ## A Pool cannot be used without overriding create()
        pool = pools.Pool()
        self.assertRaises(NotImplementedError, pool.get)


class TestIntPool2(unittest.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = IntPool(min_size=3, max_size=3)

    def test_something(self):
        self.assertEquals(len(self.pool.free_items), 3)
        ## Cover the clause in get where we get from the free list instead of creating
        ## an item on get
        gotten = self.pool.get()
        self.assertEquals(gotten, 1)


ALWAYS = RuntimeError('I always fail')
SOMETIMES = RuntimeError('I fail half the time')


class TestFan(unittest.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = IntPool(max_size=2)

    def test_with_list(self):
        list_of_input = ['agent-one', 'agent-two', 'agent-three']

        def my_callable(pool_item, next_thing):
            ## Do some "blocking" (yielding) thing
            api.sleep(0.01)
            return next_thing

        output = self.pool.fan(my_callable, list_of_input)
        self.assertEquals(list_of_input, output)

    def test_all_fail(self):
        def my_failure(pool_item, next_thing):
            raise ALWAYS
        self.assertRaises(pools.AllFailed, self.pool.fan, my_failure, range(4))

    def test_some_fail(self):
        def my_failing_callable(pool_item, next_thing):
            if next_thing % 2:
                raise SOMETIMES
            return next_thing
        self.assertRaises(pools.SomeFailed, self.pool.fan, my_failing_callable, range(4))
        
    
if __name__ == '__main__':
    unittest.main()

