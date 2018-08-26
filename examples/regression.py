"""This is a Regression Test.
"""
import eventlet
from time import time as monotonic
# from eventlet.green.time import monotonic
from eventlet import hubs
ev_sleep = eventlet.sleep

stats = []
data = {'initiated_timers': 0, 'called_timers': 0}


def timer(start_time, delay, sem):
    data['called_timers'] += 1
    stats.append((monotonic() - start_time, delay))
    sem.release()


def worker(worker_n, num_timers_a_range, ms_delay_range, sem):
    print ("Worker:             " + str(worker_n))
    hub = hubs.get_hub()
    schedule_call_global = hub.schedule_call_global
    for n in range(1, num_timers_a_range + 1):
        if float(int(n/100)) == float(n)/100:
            print ("Worker:             " + str(worker_n) + ", timer a range - progress: " + str(n)
                   + ", hub timers: "+str(hub.get_timers_count())
                   + ", cancelled: "+str(hub.timers_canceled))

        for delay in range(ms_delay_range[0], ms_delay_range[1], ms_delay_range[2]):
            delay /= 1000
            schedule_call_global(delay, timer, monotonic(), delay, sem)
            data['initiated_timers'] += 1
        ev_sleep()


def producer():
    num_workers = 10
    num_range_timers = 1000
    ms_delay_range = [1, 5001, 500]
    expected_timers = num_workers * num_range_timers * (
        int((ms_delay_range[1] - ms_delay_range[0]) / ms_delay_range[2]))
    data['expected_timers'] = expected_timers

    print ("Timers Expected:        " + str(data['expected_timers']))

    sem = eventlet.Semaphore(expected_timers)
    for n in range(0, expected_timers):
        sem.acquire()

    pool = eventlet.GreenPool()
    for n in range(1, num_workers + 1):
        pool.spawn_n(worker, n, num_range_timers, ms_delay_range, sem=sem)
    pool.waitall()

    # block for size to be back available
    hub = hubs.get_hub()
    last = 0
    start_100k = monotonic()
    for n in range(0, expected_timers):
        if data['called_timers'] != last \
                and float(int(data['called_timers'] / 100000)) == float(data['called_timers']) / 100000:

            print ("progress - called_timers: "
                   + str(data['called_timers'])
                   + ", 100K time: "+str(monotonic()-start_100k)
                   + ", hub timers: "+str(hub.get_timers_count())
                   + ", cancelled: "+str(hub.timers_canceled))
            start_100k = monotonic()
            last = data['called_timers']
        sem.acquire()


start_load = monotonic()
producer()
time_took = monotonic() - start_load

total_differential = 0
for real, expected in stats:
    total_differential += abs(real-expected)

print ("-"*79)
print ("Results: ")
print ("*"*40)
print ("Timers Expected:        " + str(data['expected_timers']))
print ("Timers Initiated:       " + str(data['initiated_timers']))
print ("Timers Executed:        " + str(data['called_timers']))
print ("Time Took:              " + str(time_took))
print ("Delay Differential Sum: " + str(total_differential))
print ("Delay Differential Avg: " + str(total_differential / len(stats)))
print ("*"*40)
print ("-"*79)
