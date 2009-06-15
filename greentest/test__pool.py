from eventlet import pool, coros, api
from greentest import LimitedTestCase
from unittest import main

class TestCoroutinePool(LimitedTestCase):
    klass = pool.Pool

    def test_execute_async(self):
        done = coros.event()
        def some_work():
            done.send()
        pool = self.klass(0, 2)
        pool.execute_async(some_work)
        done.wait()

    def test_execute(self):
        value = 'return value'
        def some_work():
            return value
        pool = self.klass(0, 2)
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

        pool = self.klass(0, 2)
        done = pool.execute(consumer)
        pool.execute_async(producer)
        done.wait()
        self.assertEquals(['cons1', 'prod', 'cons2'], results)

    def test_timer_cancel(self):
        # this test verifies that local timers are not fired 
        # outside of the context of the execute method
        timer_fired = []
        def fire_timer():
            timer_fired.append(True)
        def some_work():
            api.get_hub().schedule_call_local(0, fire_timer)
        pool = self.klass(0, 2)
        worker = pool.execute(some_work)
        worker.wait()
        api.sleep(0)
        self.assertEquals(timer_fired, [])

    def test_reentrant(self):
        pool = self.klass(0,1)
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
        
    def test_stderr_raising(self):
        # testing that really egregious errors in the error handling code 
        # (that prints tracebacks to stderr) don't cause the pool to lose 
        # any members
        import sys
        pool = self.klass(min_size=1, max_size=1)
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
            # pool.Pool change: if an exception is raised during execution of a link, 
            # the rest of the links are scheduled to be executed on the next hub iteration
            # this introduces a delay in updating pool.sem which makes pool.free() report 0
            # therefore, sleep:
            api.sleep(0)
            self.assertEqual(pool.free(), 1)
            # shouldn't block when trying to get
            t = api.exc_after(0.1, api.TimeoutError)
            try:
                pool.execute(api.sleep, 1)
            finally:
                t.cancel()
        finally:
            sys.stderr = normal_err

    def test_track_events(self):
        pool = self.klass(track_events=True)
        for x in range(6):
            pool.execute(lambda n: n, x)
        for y in range(6):
            pool.wait()

    def test_track_slow_event(self):
        pool = self.klass(track_events=True)
        def slow():
            api.sleep(0.1)
            return 'ok'
        pool.execute(slow)
        self.assertEquals(pool.wait(), 'ok')
        
    def test_pool_smash(self):
        # The premise is that a coroutine in a Pool tries to get a token out
        # of a token pool but times out before getting the token.  We verify
        # that neither pool is adversely affected by this situation.
        from eventlet import pools
        pool = self.klass(min_size=1, max_size=1)
        tp = pools.TokenPool(max_size=1)
        token = tp.get()  # empty pool
        def do_receive(tp):
            api.exc_after(0, RuntimeError())
            try:
                t = tp.get()
                self.fail("Shouldn't have recieved anything from the pool")
            except RuntimeError:
                return 'timed out'

        # the execute makes the token pool expect that coroutine, but then
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


class PoolBasicTests(LimitedTestCase):
    klass = pool.Pool

    def test_execute_async(self):
        p = self.klass(max_size=2)
        self.assertEqual(p.free(), 2)
        r = []
        def foo(a):
            r.append(a)
        evt = p.execute(foo, 1)
        self.assertEqual(p.free(), 1)
        evt.wait()
        self.assertEqual(r, [1])
        api.sleep(0)
        self.assertEqual(p.free(), 2)

        #Once the pool is exhausted, calling an execute forces a yield.

        p.execute_async(foo, 2)
        self.assertEqual(1, p.free())
        self.assertEqual(r, [1])

        p.execute_async(foo, 3)
        self.assertEqual(0, p.free())
        self.assertEqual(r, [1])

        p.execute_async(foo, 4)
        self.assertEqual(r, [1,2,3])
        api.sleep(0)
        self.assertEqual(r, [1,2,3,4])

    def test_execute(self):
        p = self.klass()
        evt = p.execute(lambda a: ('foo', a), 1)
        self.assertEqual(evt.wait(), ('foo', 1))


if __name__=='__main__':
    main()

