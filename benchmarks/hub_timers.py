#! /usr/bin/env python
from __future__ import print_function

# test timer adds & expires on hubs.hub.BaseHub

import sys
import eventlet
import random
import time

from eventlet.hubs import timer, get_hub
from eventlet.support import six


timer_count = 100000

if len(sys.argv) >= 2:
    timer_count = int(sys.argv[1])

l = []


def work(n):
    l.append(n)

timeouts = [random.uniform(0, 10) for x in six.moves.range(timer_count)]

hub = get_hub()

start = time.time()

scheduled = []

for timeout in timeouts:
    t = timer.Timer(timeout, work, timeout)
    t.schedule()

    scheduled.append(t)

hub.prepare_timers()
hub.fire_timers(time.time() + 11)
hub.prepare_timers()

end = time.time()

print("Duration: %f" % (end - start,))
