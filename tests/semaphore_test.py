import unittest
import eventlet
from eventlet import semaphore
from tests import LimitedTestCase
from tests import patcher_test


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


semaphore_tpool_code = """
from eventlet import greenthread
from eventlet import patcher
patcher.monkey_patch(thread=True)
from eventlet import tpool
import threading


lock = threading.Lock()
info = dict(thr=20)


def lock_test():
    lock.acquire()
    greenthread.sleep(0)
    lock.release()


def gt_runner(method, *args):
    method(*args)
    info['thr'] -= 1


for x in range(10):
    greenthread.spawn_n(gt_runner, tpool.execute, lock_test)
    greenthread.spawn_n(gt_runner, lock_test)

for x in xrange(20):
    greenthread.sleep(0.5)
    if not info['thr']:
        break
else:
    print 'fail'
"""


class MonkeyPatchTester(patcher_test.ProcessBase):
    def test_semaphore_with_monkey_patched_thread(self):
        output, lines = self.run_script(semaphore_tpool_code)
        self.assertEqual(lines, [''])


if __name__=='__main__':
    unittest.main()
