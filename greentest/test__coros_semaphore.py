from __future__ import with_statement
import unittest
from eventlet import api, coros

class TestSemaphore(unittest.TestCase):

    def test_bounded(self):
        # this was originally semaphore's doctest
        sem = coros.BoundedSemaphore(2, limit=3)
        self.assertEqual(sem.acquire(), True)
        self.assertEqual(sem.acquire(), True)
        api.spawn(sem.release)
        self.assertEqual(sem.acquire(), True)
        self.assertEqual(0, sem.counter)
        sem.release()
        sem.release()
        sem.release()
        api.spawn(sem.acquire)
        sem.release()
        self.assertEqual(3, sem.counter)
   
    def test_bounded_with_zero_limit(self):
        sem = coros.semaphore(0, 0)
        api.spawn(sem.acquire)
        with api.timeout(0.001):
            sem.release()


if __name__=='__main__':
    unittest.main()
