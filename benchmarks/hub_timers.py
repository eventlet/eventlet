'''Benchmark timer adds & expires on hubs.hub.BaseHub
'''
import contextlib
import random

import benchmarks
from eventlet.hubs import timer, get_hub


l = []
hub = get_hub()


def work(n):
    l.append(n)


@contextlib.contextmanager
def setup(iters):
    l[:] = []
    timeouts = [random.uniform(0, 10) for x in range(iters)]
    yield timeouts


@benchmarks.configure(manager=setup, scale_factor=3)
def benchmark_hub_timers(timeouts):
    scheduled = []

    for timeout in timeouts:
        t = timer.Timer(timeout, work, timeout)
        t.schedule()
        scheduled.append(t)

    hub.prepare_timers()
    hub.fire_timers(hub.clock() + 11)
    hub.prepare_timers()
