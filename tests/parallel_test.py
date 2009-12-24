import gc
import random 

from eventlet import api, hubs, parallel, coros
import tests

class Spawn(tests.LimitedTestCase):
    # TODO: move this test elsewhere
    def test_simple(self):
        def f(a, b=None):
            return (a,b)
        
        gt = parallel.api.  spawn(f, 1, b=2)
        self.assertEquals(gt.wait(), (1,2))

def passthru(a):
    api.sleep(0.01)
    return a
        
class GreenPool(tests.LimitedTestCase):
    def test_spawn(self):
        p = parallel.GreenPool(4)
        waiters = []
        for i in xrange(10):
            waiters.append(p.spawn(passthru, i))
        results = [waiter.wait() for waiter in waiters]
        self.assertEquals(results, list(xrange(10)))

    def test_spawn_n(self):
        p = parallel.GreenPool(4)
        results_closure = []
        def do_something(a):
            api.sleep(0.01)
            results_closure.append(a)
        for i in xrange(10):
            p.spawn(do_something, i)
        p.waitall()
        self.assertEquals(results_closure, range(10))
        
    def test_waiting(self):
        pool = parallel.GreenPool(1)
        done = coros.Event()
        def consume():
            done.wait()
        def waiter(pool):
            gt = pool.spawn(consume)
            gt.wait()
        
        waiters = []
        self.assertEqual(pool.running(), 0)
        waiters.append(api.spawn(waiter, pool))
        api.sleep(0)
        self.assertEqual(pool.waiting(), 0)
        waiters.append(api.spawn(waiter, pool))
        api.sleep(0)
        self.assertEqual(pool.waiting(), 1)
        waiters.append(api.spawn(waiter, pool))
        api.sleep(0)
        self.assertEqual(pool.waiting(), 2)
        self.assertEqual(pool.running(), 1)
        done.send(None)
        for w in waiters:
            w.wait()
        self.assertEqual(pool.waiting(), 0)
        self.assertEqual(pool.running(), 0)
        
    def test_multiple_coros(self):
        evt = coros.Event()
        results = []
        def producer():
            results.append('prod')
            evt.send()
        def consumer():
            results.append('cons1')
            evt.wait()
            results.append('cons2')

        pool = parallel.GreenPool(2)
        done = pool.spawn(consumer)
        pool.spawn_n(producer)
        done.wait()
        self.assertEquals(['cons1', 'prod', 'cons2'], results)

    def test_timer_cancel(self):
        # this test verifies that local timers are not fired 
        # outside of the context of the spawn
        timer_fired = []
        def fire_timer():
            timer_fired.append(True)
        def some_work():
            hubs.get_hub().schedule_call_local(0, fire_timer)
        pool = parallel.GreenPool(2)
        worker = pool.spawn(some_work)
        worker.wait()
        api.sleep(0)
        api.sleep(0)
        self.assertEquals(timer_fired, [])
        
    def test_reentrant(self):
        pool = parallel.GreenPool(1)
        def reenter():
            waiter = pool.spawn(lambda a: a, 'reenter')
            self.assertEqual('reenter', waiter.wait())

        outer_waiter = pool.spawn(reenter)
        outer_waiter.wait()

        evt = coros.Event()
        def reenter_async():
            pool.spawn_n(lambda a: a, 'reenter')
            evt.send('done')

        pool.spawn_n(reenter_async)
        self.assertEquals('done', evt.wait())
        
    def assert_pool_has_free(self, pool, num_free):
        def wait_long_time(e):
            e.wait()
        timer = api.exc_after(1, api.TimeoutError)
        try:
            evt = coros.Event()
            for x in xrange(num_free):
                pool.spawn(wait_long_time, evt)
                # if the pool has fewer free than we expect,
                # then we'll hit the timeout error
        finally:
            timer.cancel()

        # if the runtime error is not raised it means the pool had
        # some unexpected free items
        timer = api.exc_after(0, RuntimeError)
        try:
            self.assertRaises(RuntimeError, pool.spawn, wait_long_time, evt)
        finally:
            timer.cancel()

        # clean up by causing all the wait_long_time functions to return
        evt.send(None)
        api.sleep(0)
        api.sleep(0)
        
    def test_resize(self):
        pool = parallel.GreenPool(2)
        evt = coros.Event()
        def wait_long_time(e):
            e.wait()
        pool.spawn(wait_long_time, evt)
        pool.spawn(wait_long_time, evt)
        self.assertEquals(pool.free(), 0)
        self.assertEquals(pool.running(), 2)
        self.assert_pool_has_free(pool, 0)

        # verify that the pool discards excess items put into it
        pool.resize(1)
        
        # cause the wait_long_time functions to return, which will
        # trigger puts to the pool
        evt.send(None)
        api.sleep(0)
        api.sleep(0)
        
        self.assertEquals(pool.free(), 1)
        self.assertEquals(pool.running(), 0)
        self.assert_pool_has_free(pool, 1)

        # resize larger and assert that there are more free items
        pool.resize(2)
        self.assertEquals(pool.free(), 2)
        self.assertEquals(pool.running(), 0)
        self.assert_pool_has_free(pool, 2)
        
    def test_pool_smash(self):
        # The premise is that a coroutine in a Pool tries to get a token out
        # of a token pool but times out before getting the token.  We verify
        # that neither pool is adversely affected by this situation.
        from eventlet import pools
        pool = parallel.GreenPool(1)
        tp = pools.TokenPool(max_size=1)
        token = tp.get()  # empty out the pool
        def do_receive(tp):
            timer = api.exc_after(0, RuntimeError())
            try:
                t = tp.get()
                self.fail("Shouldn't have recieved anything from the pool")
            except RuntimeError:
                return 'timed out'
            else:
                timer.cancel()

        # the spawn makes the token pool expect that coroutine, but then
        # immediately cuts bait
        e1 = pool.spawn(do_receive, tp)
        self.assertEquals(e1.wait(), 'timed out')

        # the pool can get some random item back
        def send_wakeup(tp):
            tp.put('wakeup')
        gt = api.spawn(send_wakeup, tp)

        # now we ask the pool to run something else, which should not
        # be affected by the previous send at all
        def resume():
            return 'resumed'
        e2 = pool.spawn(resume)
        self.assertEquals(e2.wait(), 'resumed')

        # we should be able to get out the thing we put in there, too
        self.assertEquals(tp.get(), 'wakeup')
        gt.wait()
        
    def test_spawn_n_2(self):
        p = parallel.GreenPool(2)
        self.assertEqual(p.free(), 2)
        r = []
        def foo(a):
            r.append(a)
        gt = p.spawn(foo, 1)
        self.assertEqual(p.free(), 1)
        gt.wait()
        self.assertEqual(r, [1])
        api.sleep(0)
        self.assertEqual(p.free(), 2)

        #Once the pool is exhausted, spawning forces a yield.
        p.spawn_n(foo, 2)
        self.assertEqual(1, p.free())
        self.assertEqual(r, [1])

        p.spawn_n(foo, 3)
        self.assertEqual(0, p.free())
        self.assertEqual(r, [1])

        p.spawn_n(foo, 4)
        self.assertEqual(set(r), set([1,2,3]))
        api.sleep(0)
        self.assertEqual(set(r), set([1,2,3,4]))

class GreenPile(tests.LimitedTestCase):
    def test_imap(self):
        p = parallel.GreenPile(4)
        result_list = list(p.imap(passthru, xrange(10)))
        self.assertEquals(result_list, list(xrange(10)))
        
    def test_empty_map(self):
        p = parallel.GreenPile(4)
        result_iter = p.imap(passthru, [])
        self.assertRaises(StopIteration, result_iter.next)

    def test_pile(self):
        p = parallel.GreenPile(4)
        for i in xrange(10):
            p.spawn(passthru, i)
        result_list = list(p)
        self.assertEquals(result_list, list(xrange(10)))
        
    def test_pile_spawn_times_out(self):
        p = parallel.GreenPile(4)
        for i in xrange(4):
            p.spawn(passthru, i)
        # now it should be full and this should time out
        api.exc_after(0, api.TimeoutError)
        self.assertRaises(api.TimeoutError, p.spawn, passthru, "time out")
        # verify that the spawn breakage didn't interrupt the sequence
        # and terminates properly
        for i in xrange(4,10):
            p.spawn(passthru, i)
        self.assertEquals(list(p), list(xrange(10)))
        
    def test_constructing_from_pool(self):
        pool = parallel.GreenPool(2)
        pile1 = parallel.GreenPile(pool)
        pile2 = parallel.GreenPile(pool)
        def bunch_of_work(pile, unique):
            for i in xrange(10):
                pile.spawn(passthru, i + unique)
        api.spawn(bunch_of_work, pile1, 0)
        api.spawn(bunch_of_work, pile2, 100)
        api.sleep(0)
        self.assertEquals(list(pile2), list(xrange(100,110)))
        self.assertEquals(list(pile1), list(xrange(10)))
            


class StressException(Exception):
    pass

r = random.Random(0)
def pressure(arg):
    while r.random() < 0.5:
        api.sleep(r.random() * 0.001)
    if r.random() < 0.8:
        return arg
    else:
        raise StressException(arg)
        
# TODO: skip these unless explicitly demanded by the user
class Stress(tests.SilencedTestCase):
    # tests will take extra-long
    TEST_TIMEOUT=10
    def spawn_memory(self, concurrency):
        # checks that piles are strictly ordered
        # and bounded in memory
        p = parallel.GreenPile(concurrency)
        def makework(count, unique):            
            for i in xrange(count):
                token = (unique, i)
                p.spawn(pressure, token)
        
        api.spawn(makework, 1000, 1)
        api.spawn(makework, 1000, 2)
        api.spawn(makework, 1000, 3)
        p.spawn(pressure, (0,0))
        latest = [-1] * 4
        received = 0
        it = iter(p)
        initial_obj_count = len(gc.get_objects())
        while True:
            try:
                i = it.next()
                received += 1
                if received % 10 == 0:
                    gc.collect()
                    objs_created = len(gc.get_objects()) - initial_obj_count
                    self.assert_(objs_created < 200 * concurrency, objs_created)
            except StressException, exc:
                i = exc[0]
            except StopIteration:
                break
            unique, order = i
            self.assert_(latest[unique] < order)
            latest[unique] = order

    def test_memory_5(self):
        self.spawn_memory(5)
    
    def test_memory_50(self):
        self.spawn_memory(50)
        
    def test_memory_500(self):
        self.spawn_memory(50)
        
    def test_with_intpool(self):
        from eventlet import pools
        class IntPool(pools.Pool):
            def create(self):
                self.current_integer = getattr(self, 'current_integer', 0) + 1
                return self.current_integer
        
        def subtest(intpool_size, pool_size, num_executes):        
            def run(int_pool):
                token = int_pool.get()
                api.sleep(0.0001)
                int_pool.put(token)
                return token
            
            int_pool = IntPool(max_size=intpool_size)
            pool = parallel.GreenPool(pool_size)
            for ix in xrange(num_executes):
                pool.spawn(run, int_pool)
            pool.waitall()
            
        subtest(4, 7, 7)
        subtest(50, 75, 100)
        for isize in (10, 20, 30, 40, 50):
            for psize in (5, 25, 35, 50):
                subtest(isize, psize, psize)