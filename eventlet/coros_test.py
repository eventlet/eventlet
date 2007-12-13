"""\
@file coros_test.py
@author Donovan Preston, Ryan Williams

Copyright (c) 2000-2007, Linden Research, Inc.
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
from eventlet import tests
from eventlet import timer
from eventlet import coros, api

class TestEvent(tests.TestCase):
    mode = 'static'
    def setUp(self):
        # raise an exception if we're waiting forever
        self._cancel_timeout = api.exc_after(1, RuntimeError())

    def tearDown(self):
        self._cancel_timeout.cancel()

    def test_waiting_for_event(self):
        evt = coros.event()
        value = 'some stuff'
        def send_to_event():
            evt.send(value)
        api.spawn(send_to_event)
        self.assertEqual(evt.wait(), value)

    def test_multiple_waiters(self):
        evt = coros.event()
        value = 'some stuff'
        results = []
        def wait_on_event(i_am_done):
            evt.wait()
            results.append(True)
            i_am_done.send()

        waiters = []
        count = 5
        for i in range(count):
            waiters.append(coros.event())
            api.spawn(wait_on_event, waiters[-1])
        evt.send()

        for w in waiters:
            w.wait()

        self.assertEqual(len(results), count)

    def test_cancel(self):
        evt = coros.event()
        # close over the current coro so we can cancel it explicitly
        current = api.getcurrent()
        def cancel_event():
            evt.cancel(current)
        api.spawn(cancel_event)

        self.assertRaises(coros.Cancelled, evt.wait)

    def test_reset(self):
        evt = coros.event()

        # calling reset before send should throw
        self.assertRaises(AssertionError, evt.reset)
        
        value = 'some stuff'
        def send_to_event():
            evt.send(value)
        api.spawn(send_to_event)
        self.assertEqual(evt.wait(), value)

        # now try it again, and we should get the same exact value,
        # and we shouldn't be allowed to resend without resetting
        value2 = 'second stuff'
        self.assertRaises(AssertionError, evt.send, value2)
        self.assertEqual(evt.wait(), value)

        # reset and everything should be happy
        evt.reset()
        def send_to_event2():
            evt.send(value2)
        api.spawn(send_to_event2)
        self.assertEqual(evt.wait(), value2)

class TestCoroutinePool(tests.TestCase):
    mode = 'static'
    def setUp(self):
        # raise an exception if we're waiting forever
        self._cancel_timeout = api.exc_after(1, RuntimeError())

    def tearDown(self):
        self._cancel_timeout.cancel()

    def test_execute_async(self):
        done = coros.event()
        def some_work():
            done.send()
        pool = coros.CoroutinePool(0, 2)
        pool.execute_async(some_work)
        done.wait()

    def test_execute(self):
        value = 'return value'
        def some_work():
            return value
        pool = coros.CoroutinePool(0, 2)
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

        pool = coros.CoroutinePool(0, 2)
        done = pool.execute(consumer)
        pool.execute_async(producer)
        done.wait()
        self.assertEquals(['cons1', 'prod', 'cons2'], results)

    def test_timer_cancel(self):
        def some_work():
            t = timer.Timer(5, lambda: None)
            t.schedule()
            return t
        pool = coros.CoroutinePool(0, 2)
        worker = pool.execute(some_work)
        t = worker.wait()
        api.sleep(0)
        self.assertEquals(t.cancelled, True)

if __name__ == '__main__':
    tests.main()
