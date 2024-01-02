"""Test context switching performance of threading and eventlet"""

import threading
import time

import eventlet
import eventlet.hubs


CONTEXT_SWITCHES = 100000


def run(event, wait_event):
    counter = 0
    while counter <= CONTEXT_SWITCHES:
        wait_event.wait()
        wait_event.reset()
        counter += 1
        event.send()


def test_eventlet():
    event1 = eventlet.event.Event()
    event2 = eventlet.event.Event()
    event1.send()
    thread1 = eventlet.spawn(run, event1, event2)
    thread2 = eventlet.spawn(run, event2, event1)

    thread1.wait()
    thread2.wait()


class BenchThread(threading.Thread):
    def __init__(self, event, wait_event):
        threading.Thread.__init__(self)
        self.counter = 0
        self.event = event
        self.wait_event = wait_event

    def run(self):
        while self.counter <= CONTEXT_SWITCHES:
            self.wait_event.wait()
            self.wait_event.clear()
            self.counter += 1
            self.event.set()


def test_thread():
    event1 = threading.Event()
    event2 = threading.Event()
    event1.set()
    thread1 = BenchThread(event1, event2)
    thread2 = BenchThread(event2, event1)
    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()


print("Testing with %d context switches" % CONTEXT_SWITCHES)
start = time.time()
test_thread()
print("threading: %.02f seconds" % (time.time() - start))

try:
    eventlet.hubs.use_hub("eventlet.hubs.epolls")
    start = time.time()
    test_eventlet()
    print("epoll:     %.02f seconds" % (time.time() - start))
except:
    print("epoll hub unavailable")

try:
    eventlet.hubs.use_hub("eventlet.hubs.kqueue")
    start = time.time()
    test_eventlet()
    print("kqueue:    %.02f seconds" % (time.time() - start))
except:
    print("kqueue hub unavailable")

try:
    eventlet.hubs.use_hub("eventlet.hubs.poll")
    start = time.time()
    test_eventlet()
    print("poll:      %.02f seconds" % (time.time() - start))
except:
    print("poll hub unavailable")

try:
    eventlet.hubs.use_hub("eventlet.hubs.selects")
    start = time.time()
    test_eventlet()
    print("select:    %.02f seconds" % (time.time() - start))
except:
    print("select hub unavailable")
