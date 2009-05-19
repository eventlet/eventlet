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

import sys

from eventlet import api
from eventlet import channel
from eventlet import coros
from eventlet import pools
from greentest import tests
from eventlet import timer

class IntPool(pools.Pool):
    def create(self):
        self.current_integer = getattr(self, 'current_integer', 0) + 1
        return self.current_integer


class TestIntPool(tests.TestCase):
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

    def test_ordering(self):
        # normal case is that items come back out in the
        # same order they are put
        one, two = self.pool.get(), self.pool.get()
        self.pool.put(one)
        self.pool.put(two)
        self.assertEquals(self.pool.get(), one)
        self.assertEquals(self.pool.get(), two)

    def test_putting_to_queue(self):
        timer = api.exc_after(0.1, api.TimeoutError)
        size = 2
        self.pool = IntPool(min_size=0, max_size=size)
        queue = coros.queue()
        results = []
        def just_put(pool_item, index):
            self.pool.put(pool_item)
            queue.send(index)
        for index in xrange(size + 1):
            pool_item = self.pool.get()
            api.spawn(just_put, pool_item, index)

        while results != range(size + 1):
            x = queue.wait()
            results.append(x)
        timer.cancel()


class TestAbstract(tests.TestCase):
    mode = 'static'
    def test_abstract(self):
        ## Going for 100% coverage here
        ## A Pool cannot be used without overriding create()
        pool = pools.Pool()
        self.assertRaises(NotImplementedError, pool.get)


class TestIntPool2(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = IntPool(min_size=3, max_size=3)

    def test_something(self):
        self.assertEquals(len(self.pool.free_items), 3)
        ## Cover the clause in get where we get from the free list instead of creating
        ## an item on get
        gotten = self.pool.get()
        self.assertEquals(gotten, 1)


class TestOrderAsStack(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = IntPool(max_size=3, order_as_stack=True)

    def test_ordering(self):
        # items come out in the reverse order they are put
        one, two = self.pool.get(), self.pool.get()
        self.pool.put(one)
        self.pool.put(two)
        self.assertEquals(self.pool.get(), two)
        self.assertEquals(self.pool.get(), one)


class RaisePool(pools.Pool):
    def create(self):
        raise RuntimeError()


class TestCreateRaises(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = RaisePool(max_size=3)

    def test_it(self):
        self.assertEquals(self.pool.free(), 3)
        self.assertRaises(RuntimeError, self.pool.get)
        self.assertEquals(self.pool.free(), 3)


ALWAYS = RuntimeError('I always fail')
SOMETIMES = RuntimeError('I fail half the time')


class TestTookTooLong(Exception):
    pass

class TestFan(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.timer = api.exc_after(1, TestTookTooLong())
        self.pool = IntPool(max_size=2)

    def tearDown(self):
        self.timer.cancel()

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


class TestCoroutinePool(tests.TestCase):
    mode = 'static'
    def setUp(self):
        # raise an exception if we're waiting forever
        self._cancel_timeout = api.exc_after(1, TestTookTooLong())

    def tearDown(self):
        self._cancel_timeout.cancel()

    def test_execute_async(self):
        done = coros.event()
        def some_work():
            done.send()
        pool = pools.CoroutinePool(0, 2)
        pool.execute_async(some_work)
        done.wait()

    def test_execute(self):
        value = 'return value'
        def some_work():
            return value
        pool = pools.CoroutinePool(0, 2)
        worker = pool.execute(some_work)
        self.assertEqual(value, worker.wait())

    def test_multiple_coros(self):
        evt = coros.event()
        results = []
        def producer():
            results.append('prod')
            evt.send()

        def consumer():
            results.append('cons1')
            evt.wait()
            results.append('cons2')

        pool = pools.CoroutinePool(0, 2)
        done = pool.execute(consumer)
        pool.execute_async(producer)
        done.wait()
        self.assertEquals(['cons1', 'prod', 'cons2'], results)

    def test_timer_cancel(self):
        def some_work():
            t = timer.Timer(5, lambda: None)
            t.autocancellable = True
            t.schedule()
            return t
        pool = pools.CoroutinePool(0, 2)
        worker = pool.execute(some_work)
        t = worker.wait()
        api.sleep(0)
        self.assertEquals(t.cancelled, True)

    def test_reentrant(self):
        pool = pools.CoroutinePool(0,1)
        def reenter():
            waiter = pool.execute(lambda a: a, 'reenter')
            self.assertEqual('reenter', waiter.wait())

        outer_waiter = pool.execute(reenter)
        outer_waiter.wait()

        evt = coros.event()
        def reenter_async():
            pool.execute_async(lambda a: a, 'reenter')
            evt.send('done')

        pool.execute_async(reenter_async)
        evt.wait()

    def test_horrible_main_loop_death(self):
        # testing the case that causes the run_forever
        # method to exit unwantedly
        pool = pools.CoroutinePool(min_size=1, max_size=1)
        def crash(*args, **kw):
            raise RuntimeError("Whoa")
        class FakeFile(object):
            write = crash

        # we're going to do this by causing the traceback.print_exc in
        # safe_apply to raise an exception and thus exit _main_loop
        normal_err = sys.stderr
        try:
            sys.stderr = FakeFile()
            waiter = pool.execute(crash)
            self.assertRaises(RuntimeError, waiter.wait)
            # the pool should have something free at this point since the
            # waiter returned
            self.assertEqual(pool.free(), 1)
            # shouldn't block when trying to get
            t = api.exc_after(0.1, api.TimeoutError)
            self.assert_(pool.get())
            t.cancel()
        finally:
            sys.stderr = normal_err

    def test_track_events(self):
        pool = pools.CoroutinePool(track_events=True)
        for x in range(6):
            pool.execute(lambda n: n, x)
        for y in range(6):
            pool.wait()

    def test_track_slow_event(self):
        pool = pools.CoroutinePool(track_events=True)
        def slow():
            api.sleep(0.1)
            return 'ok'
        pool.execute(slow)
        self.assertEquals(pool.wait(), 'ok')

    def test_channel_smash(self):
        # The premise is that the coroutine in the pool exhibits an
        # interest in receiving data from the channel, but then times
        # out and gets recycled, so it ceases to care about what gets
        # sent over the channel.  The pool should be able to tell the
        # channel about the sudden change of heart, or else, when we
        # eventually do send something into the channel it will catch
        # the coroutine pool's coroutine in an awkward place, losing
        # the data that we're sending.
        from eventlet import pools
        pool = pools.CoroutinePool(min_size=1, max_size=1)
        tp = pools.TokenPool(max_size=1)
        token = tp.get()  # empty pool
        def do_receive(tp):
            api.exc_after(0, RuntimeError())
            try:
                t = tp.get()
                self.fail("Shouldn't have recieved anything from the pool")
            except RuntimeError:
                return 'timed out'

        # the execute makes the pool expect that coroutine, but then
        # immediately cuts bait
        e1 = pool.execute(do_receive, tp)
        self.assertEquals(e1.wait(), 'timed out')

        # the pool can get some random item back
        def send_wakeup(tp):
            tp.put('wakeup')
        api.spawn(send_wakeup, tp)

        # now we ask the pool to run something else, which should not
        # be affected by the previous send at all
        def resume():
            return 'resumed'
        e2 = pool.execute(resume)
        self.assertEquals(e2.wait(), 'resumed')

        # we should be able to get out the thing we put in there, too
        self.assertEquals(tp.get(), 'wakeup')

    def test_channel_death(self):
        # In here, we have a coroutine trying to receive data from a
        # channel, but timing out immediately and dying. The channel
        # should be smart enough to not try to send data to a dead
        # coroutine, because if it tries to, it'll lose the data.
        from eventlet import pools
        tp = pools.TokenPool(max_size=1)
        token = tp.get()
        e1 = coros.event()
        def do_receive(evt, tp):
            api.exc_after(0, RuntimeError())
            try:
                t = tp.get()
                evt.send(t)
            except RuntimeError:
                evt.send('timed out')

        # the execute gets the pool to add a waiter, but then kills
        # itself off
        api.spawn(do_receive, e1, tp)
        self.assertEquals(e1.wait(), 'timed out')

        def send_wakeup(tp):
            tp.put('wakeup')
        api.spawn(send_wakeup, tp)

        # should be able to retrieve the message
        self.assertEquals(tp.get(), 'wakeup')


if __name__ == '__main__':
    tests.main()

