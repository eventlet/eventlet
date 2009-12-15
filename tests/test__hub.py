import unittest
from tests import SilencedTestCase
import time
from eventlet import api
from eventlet.green import socket

DELAY = 0.1


class TestScheduleCall(unittest.TestCase):

    def test_local(self):
        lst = [1]
        api.spawn(api.get_hub().schedule_call_local, DELAY, lst.pop)
        api.sleep(DELAY*2)
        assert lst == [1], lst

    def test_global(self):
        lst = [1]
        api.spawn(api.get_hub().schedule_call_global, DELAY, lst.pop)
        api.sleep(DELAY*2)
        assert lst == [], lst

        
class TestDebug(unittest.TestCase):
    def test_debug(self):
        api.get_hub().debug = True
        self.assert_(api.get_hub().debug)
        api.get_hub().debug = False        
        self.assert_(not api.get_hub().debug)


class TestExceptionInMainloop(SilencedTestCase):

    def test_sleep(self):
        # even if there was an error in the mainloop, the hub should continue to work
        start = time.time()
        api.sleep(DELAY)
        delay = time.time() - start

        assert delay >= DELAY*0.9, 'sleep returned after %s seconds (was scheduled for %s)' % (delay, DELAY)

        def fail():
            1/0

        api.get_hub().schedule_call_global(0, fail)

        start = time.time()
        api.sleep(DELAY)
        delay = time.time() - start

        assert delay >= DELAY*0.9, 'sleep returned after %s seconds (was scheduled for %s)' % (delay, DELAY)


if __name__=='__main__':
    unittest.main()

