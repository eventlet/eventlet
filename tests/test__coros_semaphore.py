import unittest
from eventlet import api, coros
from tests import LimitedTestCase

class TestSemaphore(LimitedTestCase):

    def test_bounded(self):
        # this was originally semaphore's doctest
        sem = coros.BoundedSemaphore(2, limit=3)
        self.assertEqual(sem.acquire(), True)
        self.assertEqual(sem.acquire(), True)
        api.spawn(sem.release)
        self.assertEqual(sem.acquire(), True)
        self.assertEqual(-3, sem.balance)
        sem.release()
        sem.release()
        sem.release()
        api.spawn(sem.acquire)
        sem.release()
        self.assertEqual(3, sem.balance)
   
    def test_bounded_with_zero_limit(self):
        sem = coros.semaphore(0, 0)
        api.spawn(sem.acquire)
        sem.release()


if __name__=='__main__':
    unittest.main()
