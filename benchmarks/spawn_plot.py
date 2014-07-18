#!/usr/bin/env python
'''
    Compare spawn to spawn_n, among other things.

    This script will generate a number of "properties" files for the
    Hudson plot plugin
'''

import os
import eventlet
import benchmarks

DATA_DIR = 'plot_data'

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


def write_result(filename, best):
    fd = open(os.path.join(DATA_DIR, filename), 'w')
    fd.write('YVALUE=%s' % best)
    fd.close()


def cleanup():
    eventlet.sleep(0.2)

iters = 10000
best = benchmarks.measure_best(
    5, iters,
    'pass',
    cleanup,
    eventlet.sleep)

write_result('eventlet.sleep_main', best[eventlet.sleep])

gt = eventlet.spawn(
    benchmarks.measure_best, 5, iters,
    'pass',
    cleanup,
    eventlet.sleep)
best = gt.wait()
write_result('eventlet.sleep_gt', best[eventlet.sleep])


def dummy(i=None):
    return i


def run_spawn():
    eventlet.spawn(dummy, 1)


def run_spawn_n():
    eventlet.spawn_n(dummy, 1)


def run_spawn_n_kw():
    eventlet.spawn_n(dummy, i=1)


best = benchmarks.measure_best(
    5, iters,
    'pass',
    cleanup,
    run_spawn_n,
    run_spawn,
    run_spawn_n_kw)
write_result('eventlet.spawn', best[run_spawn])
write_result('eventlet.spawn_n', best[run_spawn_n])
write_result('eventlet.spawn_n_kw', best[run_spawn_n_kw])

pool = None


def setup():
    global pool
    pool = eventlet.GreenPool(iters)


def run_pool_spawn():
    pool.spawn(dummy, 1)


def run_pool_spawn_n():
    pool.spawn_n(dummy, 1)


def cleanup_pool():
    pool.waitall()


best = benchmarks.measure_best(
    3, iters,
    setup,
    cleanup_pool,
    run_pool_spawn,
    run_pool_spawn_n,
)
write_result('eventlet.GreenPool.spawn', best[run_pool_spawn])
write_result('eventlet.GreenPool.spawn_n', best[run_pool_spawn_n])
