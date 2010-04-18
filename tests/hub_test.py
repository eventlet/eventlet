from tests import LimitedTestCase, main
import time
import eventlet
from eventlet import hubs
from eventlet.green import socket

DELAY = 0.001
def noop():
    pass

class TestTimerCleanup(LimitedTestCase):
    def test_cancel_accumulated(self):
        hub = hubs.get_hub()
        start_timers = len(hub.timers)
        start_cancelled = hub.timers_cancelled
        for i in xrange(2000):
            t = hubs.get_hub().schedule_call_global(60, noop)
            eventlet.sleep()
            self.assert_(hub.timers_cancelled < len(hub.timers))
            t.cancel()
            self.assert_(hub.timers_cancelled < len(hub.timers))
        # there should be fewer than 1000 new timers and cancelled
        self.assert_(len(hub.timers) < start_timers + 1000)
        self.assert_(hub.timers_cancelled < 1000)
    
    def test_cancel_proportion(self):
        # if fewer than half the pending timers are cancelled, it should
        # not clean them out
        hub = hubs.get_hub()
        uncancelled_timers = []
        start_timers = len(hub.timers)
        start_cancelled = hub.timers_cancelled
        for i in xrange(1000):
            # 2/3rds of new timers are uncancelled
            t = hubs.get_hub().schedule_call_global(60, noop)
            t2 = hubs.get_hub().schedule_call_global(60, noop)
            t3 = hubs.get_hub().schedule_call_global(60, noop)
            eventlet.sleep()
            self.assert_(hub.timers_cancelled < len(hub.timers))
            t.cancel()
            self.assert_(hub.timers_cancelled < len(hub.timers))
            uncancelled_timers.append(t2)
            uncancelled_timers.append(t3)
        # 3000 new timers, plus one new one from the sleeps
        self.assertEqual(len(hub.timers), start_timers + 3001)
        self.assertEqual(hub.timers_cancelled, start_cancelled + 1000)
        for t in uncancelled_timers:
            t.cancel()
            self.assert_(hub.timers_cancelled < len(hub.timers))
        eventlet.sleep()
        

class TestScheduleCall(LimitedTestCase):
    def test_local(self):
        lst = [1]
        eventlet.spawn(hubs.get_hub().schedule_call_local, DELAY, lst.pop)
        eventlet.sleep(0)
        eventlet.sleep(DELAY*2)
        assert lst == [1], lst

    def test_global(self):
        lst = [1]
        eventlet.spawn(hubs.get_hub().schedule_call_global, DELAY, lst.pop)
        eventlet.sleep(0)
        eventlet.sleep(DELAY*2)
        assert lst == [], lst
        
    def test_ordering(self):
        lst = []
        hubs.get_hub().schedule_call_global(DELAY*2, lst.append, 3)
        hubs.get_hub().schedule_call_global(DELAY, lst.append, 1)
        hubs.get_hub().schedule_call_global(DELAY, lst.append, 2)
        while len(lst) < 3:
            eventlet.sleep(DELAY)
        self.assertEquals(lst, [1,2,3])

        
class TestDebug(LimitedTestCase):
    def test_debug_listeners(self):
        hubs.get_hub().set_debug_listeners(True)
        hubs.get_hub().set_debug_listeners(False)

    def test_timer_exceptions(self):
        hubs.get_hub().set_timer_exceptions(True)
        hubs.get_hub().set_timer_exceptions(False)
        

class TestExceptionInMainloop(LimitedTestCase):
    def test_sleep(self):
        # even if there was an error in the mainloop, the hub should continue to work
        start = time.time()
        eventlet.sleep(DELAY)
        delay = time.time() - start

        assert delay >= DELAY*0.9, 'sleep returned after %s seconds (was scheduled for %s)' % (delay, DELAY)

        def fail():
            1//0

        hubs.get_hub().schedule_call_global(0, fail)

        start = time.time()
        eventlet.sleep(DELAY)
        delay = time.time() - start

        assert delay >= DELAY*0.9, 'sleep returned after %s seconds (was scheduled for %s)' % (delay, DELAY)


class TestHubSelection(LimitedTestCase):
    def test_explicit_hub(self):
        if getattr(hubs.get_hub(), 'uses_twisted_reactor', None):
            # doesn't work with twisted
            return
        oldhub = hubs.get_hub()
        try:
            hubs.use_hub(Foo)
            self.assert_(isinstance(hubs.get_hub(), Foo), hubs.get_hub())
        finally:
            hubs._threadlocal.hub = oldhub



class Foo(object):
    pass

if __name__=='__main__':
    main()

