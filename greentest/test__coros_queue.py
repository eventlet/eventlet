from greentest import LimitedTestCase
from unittest import main
from eventlet import api, coros

def waiting(queue):
    try:
        return len(queue.sem._waiters)
    except AttributeError:
        return len(queue.sem.lower_bound._waiters)

class TestQueue(LimitedTestCase):

    def test_send_first(self):
        q = coros.queue()
        q.send('hi')
        self.assertEquals(q.wait(), 'hi')

    def test_send_exception_first(self):
        q = coros.queue()
        q.send(exc=RuntimeError())
        self.assertRaises(RuntimeError, q.wait)

    def test_send_last(self):
        q = coros.queue()
        def waiter(q):
            timer = api.exc_after(0.1, api.TimeoutError)
            self.assertEquals(q.wait(), 'hi2')
            timer.cancel()

        api.spawn(waiter, q)
        api.sleep(0)
        api.sleep(0)
        q.send('hi2')

    def test_max_size(self):
        q = coros.queue(2)
        results = []

        def putter(q):
            q.send('a')
            results.append('a')
            q.send('b')
            results.append('b')
            q.send('c')
            results.append('c')

        api.spawn(putter, q)
        api.sleep(0)
        self.assertEquals(results, ['a', 'b'])
        self.assertEquals(q.wait(), 'a')
        api.sleep(0)
        self.assertEquals(results, ['a', 'b', 'c'])
        self.assertEquals(q.wait(), 'b')
        self.assertEquals(q.wait(), 'c')

    def test_zero_max_size(self):
        q = coros.queue(0)
        def sender(evt, q):
            q.send('hi')
            evt.send('done')

        def receiver(evt, q):
            x = q.wait()
            evt.send(x)

        e1 = coros.event()
        e2 = coros.event()

        api.spawn(sender, e1, q)
        api.sleep(0)
        self.assert_(not e1.ready())
        api.spawn(receiver, e2, q)
        self.assertEquals(e2.wait(),'hi')
        self.assertEquals(e1.wait(),'done')

    def test_multiple_waiters(self):
        # tests that multiple waiters get their results back
        q = coros.queue()

        def waiter(q, evt):
            evt.send(q.wait())

        sendings = ['1', '2', '3', '4']
        evts = [coros.event() for x in sendings]
        for i, x in enumerate(sendings):
            api.spawn(waiter, q, evts[i])

        api.sleep(0.01) # get 'em all waiting

        results = set()
        def collect_pending_results():
            for i, e in enumerate(evts):
                timer = api.exc_after(0.001, api.TimeoutError)
                try:
                    x = e.wait()
                    results.add(x)
                    timer.cancel()
                except api.TimeoutError:
                    pass  # no pending result at that event
            return len(results)
        q.send(sendings[0])
        self.assertEquals(collect_pending_results(), 1)
        q.send(sendings[1])
        self.assertEquals(collect_pending_results(), 2)
        q.send(sendings[2])
        q.send(sendings[3])
        self.assertEquals(collect_pending_results(), 4)

    def test_waiters_that_cancel(self):
        q = coros.queue()

        def do_receive(q, evt):
            api.exc_after(0, RuntimeError())
            try:
                result = q.wait()
                evt.send(result)
            except RuntimeError:
                evt.send('timed out')


        evt = coros.event()
        api.spawn(do_receive, q, evt)
        self.assertEquals(evt.wait(), 'timed out')

        q.send('hi')
        self.assertEquals(q.wait(), 'hi')

    def test_senders_that_die(self):
        q = coros.queue()

        def do_send(q):
            q.send('sent')

        api.spawn(do_send, q)
        self.assertEquals(q.wait(), 'sent')

    def test_two_waiters_one_dies(self):
        def waiter(q, evt):
            evt.send(q.wait())
        def do_receive(q, evt):
            api.exc_after(0, RuntimeError())
            try:
                result = q.wait()
                evt.send(result)
            except RuntimeError:
                evt.send('timed out')

        q = coros.queue()
        dying_evt = coros.event()
        waiting_evt = coros.event()
        api.spawn(do_receive, q, dying_evt)
        api.spawn(waiter, q, waiting_evt)
        api.sleep(0)
        q.send('hi')
        self.assertEquals(dying_evt.wait(), 'timed out')
        self.assertEquals(waiting_evt.wait(), 'hi')

    def test_two_bogus_waiters(self):
        def do_receive(q, evt):
            api.exc_after(0, RuntimeError())
            try:
                result = q.wait()
                evt.send(result)
            except RuntimeError:
                evt.send('timed out')

        q = coros.queue()
        e1 = coros.event()
        e2 = coros.event()
        api.spawn(do_receive, q, e1)
        api.spawn(do_receive, q, e2)
        api.sleep(0)
        q.send('sent')
        self.assertEquals(e1.wait(), 'timed out')
        self.assertEquals(e2.wait(), 'timed out')
        self.assertEquals(q.wait(), 'sent')
                
    def test_waiting(self):
        def do_wait(q, evt):
            result = q.wait()
            evt.send(result)

        q = coros.queue()
        e1 = coros.event()
        api.spawn(do_wait, q, e1)
        api.sleep(0)
        self.assertEquals(1, waiting(q))
        q.send('hi')
        api.sleep(0)
        self.assertEquals(0, waiting(q))
        self.assertEquals('hi', e1.wait())
        self.assertEquals(0, waiting(q))

if __name__=='__main__':
    main()
