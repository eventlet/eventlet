# @author Donovan Preston, Ryan Williams
#
# Copyright (c) 2000-2007, Linden Research, Inc.
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

from unittest import TestCase, main
from eventlet import coros, api

class TestEvent(TestCase):
    mode = 'static'
    def setUp(self):
        # raise an exception if we're waiting forever
        self._cancel_timeout = api.exc_after(1, RuntimeError('test takes too long'))

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

    def test_double_exception(self):
        evt = coros.event()
        # send an exception through the event
        evt.send(exc=RuntimeError('from test_double_exception'))
        self.assertRaises(RuntimeError, evt.wait)
        evt.reset()
        # shouldn't see the RuntimeError again
        api.exc_after(0.001, api.TimeoutError('from test_double_exception'))
        self.assertRaises(api.TimeoutError, evt.wait)


class IncrActor(coros.Actor):
    def received(self, evt):
        self.value = getattr(self, 'value', 0) + 1
        if evt: evt.send()


class TestActor(TestCase):
    mode = 'static'
    def setUp(self):
        # raise an exception if we're waiting forever
        self._cancel_timeout = api.exc_after(1, api.TimeoutError())
        self.actor = IncrActor()

    def tearDown(self):
        self._cancel_timeout.cancel()
        api.kill(self.actor._killer)

    def test_cast(self):
        evt = coros.event()
        self.actor.cast(evt)
        evt.wait()
        evt.reset()
        self.assertEqual(self.actor.value, 1)
        self.actor.cast(evt)
        evt.wait()
        self.assertEqual(self.actor.value, 2)

    def test_cast_multi_1(self):
        # make sure that both messages make it in there
        evt = coros.event()
        evt1 = coros.event()
        self.actor.cast(evt)
        self.actor.cast(evt1)
        evt.wait()
        evt1.wait()
        self.assertEqual(self.actor.value, 2)

    def test_cast_multi_2(self):
        # the actor goes through a slightly different code path if it
        # is forced to enter its event loop prior to any cast()s
        api.sleep(0)
        self.test_cast_multi_1()

    def test_sleeping_during_received(self):
        # ensure that even if the received method cooperatively
        # yields, eventually all messages are delivered
        msgs = []
        waiters = []
        def received( (message, evt) ):
            api.sleep(0)
            msgs.append(message)
            evt.send()
        self.actor.received = received

        waiters.append(coros.event())
        self.actor.cast( (1, waiters[-1]))
        api.sleep(0)
        waiters.append(coros.event())
        self.actor.cast( (2, waiters[-1]) )
        waiters.append(coros.event())
        self.actor.cast( (3, waiters[-1]) )
        api.sleep(0)
        waiters.append(coros.event())
        self.actor.cast( (4, waiters[-1]) )
        waiters.append(coros.event())
        self.actor.cast( (5, waiters[-1]) )
        for evt in waiters:
            evt.wait()
        self.assertEqual(msgs, [1,2,3,4,5])

    def test_raising_received(self):
        msgs = []
        def received( (message, evt) ):
            evt.send()
            if message == 'fail':
                raise RuntimeError()
            else:
                msgs.append(message)

        self.actor.received = received

        evt = coros.event()
        self.actor.cast( ('fail', evt) )
        evt.wait()
        evt.reset()
        self.actor.cast( ('should_appear', evt) )
        evt.wait()
        self.assertEqual(['should_appear'], msgs)

    def test_multiple(self):
        self.actor = IncrActor(concurrency=2)
        total = [0]
        def received( (func, ev, value) ):
            func()
            total[0] += value
            ev.send()
        self.actor.received = received

        def onemoment():
            api.sleep(0.1)

        evt = coros.event()
        evt1 = coros.event()

        self.actor.cast( (onemoment, evt, 1) )
        self.actor.cast( (lambda: None, evt1, 2) )

        evt1.wait()
        self.assertEqual(total[0], 2)
        # both coroutines should have been used
        self.assertEqual(self.actor._pool.current_size, 2)
        api.sleep(0)
        self.assertEqual(self.actor._pool.free(), 1)
        evt.wait()
        self.assertEqual(total[0], 3)
        api.sleep(0)
        self.assertEqual(self.actor._pool.free(), 2)


if __name__ == '__main__':
    main()
