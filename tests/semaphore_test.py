import time
import unittest

import eventlet
from eventlet import semaphore
from tests import LimitedTestCase


class TestSemaphore(LimitedTestCase):

    def test_bounded(self):
        sem = semaphore.CappedSemaphore(2, limit=3)
        self.assertEqual(sem.acquire(), True)
        self.assertEqual(sem.acquire(), True)
        gt1 = eventlet.spawn(sem.release)
        self.assertEqual(sem.acquire(), True)
        self.assertEqual(-3, sem.balance)
        sem.release()
        sem.release()
        sem.release()
        gt2 = eventlet.spawn(sem.acquire)
        sem.release()
        self.assertEqual(3, sem.balance)
        gt1.wait()
        gt2.wait()

    def test_bounded_with_zero_limit(self):
        sem = semaphore.CappedSemaphore(0, 0)
        gt = eventlet.spawn(sem.acquire)
        sem.release()
        gt.wait()

    def test_non_blocking(self):
        sem = semaphore.Semaphore(0)
        self.assertEqual(sem.acquire(blocking=False), False)

    def test_timeout(self):
        sem = semaphore.Semaphore(0)
        start = time.time()
        self.assertEqual(sem.acquire(timeout=0.1), False)
        self.assertTrue(time.time() - start >= 0.1)

    def test_timeout_non_blocking(self):
        sem = semaphore.Semaphore()
        self.assertRaises(ValueError, sem.acquire, blocking=False, timeout=1)


if __name__ == '__main__':
    unittest.main()
