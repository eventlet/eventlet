import sys
from eventlet import coropool, coros, api
from greentest import LimitedTestCase
from unittest import main

class TestCoroutinePool(LimitedTestCase):
    klass = coropool.Pool

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


class PoolBasicTests(LimitedTestCase):
    klass = coropool.Pool

    def test_execute_async(self):
        p = self.klass(max_size=2)
        r = []
        def foo(a):
            r.append(a)
        evt = p.execute(foo, 1)
        evt.wait()
        assert r == [1], r

        #Once the pool is exhausted, calling an execute forces a yield.

        p.execute_async(foo, 2)
        assert r == [1], r
        assert 0 == p.free()
        p.execute_async(foo, 3)
        assert r == [1, 2], r
        assert 0 == p.free()
        p.execute_async(foo, 4)
        assert r == [1,2,3], r
        api.sleep(0)
        assert r == [1,2,3,4], r

    def test_execute(self):
        p = self.klass()
        evt = p.execute(lambda a: ('foo', a), 1)
        assert evt.wait() == ('foo', 1)


if __name__=='__main__':
    main()

