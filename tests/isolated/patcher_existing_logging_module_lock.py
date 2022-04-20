import logging
import eventlet.patcher
eventlet.patcher.monkey_patch(thread=True)
import threading


def take_and_release():
    try:
        logging._lock.acquire()
    finally:
        logging._lock.release()

assert logging._lock.acquire()
t = threading.Thread(target=take_and_release)
t.daemon = True
t.start()

t.join(timeout=0.1)
# we should timeout, and the thread is still blocked waiting on the lock
assert t.is_alive()

logging._lock.release()
t.join(timeout=0.1)
assert not t.is_alive()
print('pass')
