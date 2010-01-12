from tests import LimitedTestCase, SilencedTestCase, main
import time
from eventlet import api
from eventlet import hubs
from eventlet.green import socket

DELAY = 0.001

class TestScheduleCall(LimitedTestCase):
    def test_local(self):
        lst = [1]
        api.spawn(hubs.get_hub().schedule_call_local, DELAY, lst.pop)
        api.sleep(0)
        api.sleep(DELAY*2)
        assert lst == [1], lst

    def test_global(self):
        lst = [1]
        api.spawn(hubs.get_hub().schedule_call_global, DELAY, lst.pop)
        api.sleep(0)
        api.sleep(DELAY*2)
        assert lst == [], lst
        
    def test_ordering(self):
        lst = []
        hubs.get_hub().schedule_call_global(DELAY*2, lst.append, 3)
        hubs.get_hub().schedule_call_global(DELAY, lst.append, 1)
        hubs.get_hub().schedule_call_global(DELAY, lst.append, 2)
        while len(lst) < 3:
            api.sleep(DELAY)
        self.assertEquals(lst, [1,2,3])

        
class TestDebug(LimitedTestCase):
    def test_debug(self):
        hubs.get_hub().debug = True
        self.assert_(hubs.get_hub().debug)
        hubs.get_hub().debug = False        
        self.assert_(not hubs.get_hub().debug)


class TestExceptionInMainloop(SilencedTestCase):
    def test_sleep(self):
        # even if there was an error in the mainloop, the hub should continue to work
        start = time.time()
        api.sleep(DELAY)
        delay = time.time() - start

        assert delay >= DELAY*0.9, 'sleep returned after %s seconds (was scheduled for %s)' % (delay, DELAY)

        def fail():
            1/0

        hubs.get_hub().schedule_call_global(0, fail)

        start = time.time()
        api.sleep(DELAY)
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

