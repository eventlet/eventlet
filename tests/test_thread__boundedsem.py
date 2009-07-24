"""Test that BoundedSemaphore with a very high bound is as good as unbounded one"""
from eventlet import coros
from eventlet.green import thread

def allocate_lock():
    return coros.semaphore(1, 9999)

thread.allocate_lock = allocate_lock
thread.LockType = coros.BoundedSemaphore

execfile('test_thread.py')
