import unittest
from eventlet.api import call_after, spawn, sleep

class test(unittest.TestCase):

    def setUp(self):
        self.lst = [1]

    def test_timer_fired(self):
        
        def func():
            call_after(0.1, self.lst.pop)
            sleep(0.2)

        spawn(func)
        assert self.lst == [1], self.lst
        sleep(0.3)
        assert self.lst == [], self.lst

    def test_timer_cancelled_upon_greenlet_exit(self):
        
        def func():
            call_after(0.1, self.lst.pop)

        spawn(func)
        assert self.lst == [1], self.lst
        sleep(0.2)
        assert self.lst == [1], self.lst

    def test_spawn_is_not_cancelled(self):

        def func():
            spawn(self.lst.pop)
            # exiting immediatelly, but self.lst.pop must be called
        spawn(func)
        sleep(0.1)
        assert self.lst == [], self.lst


if __name__=='__main__':
    unittest.main()

