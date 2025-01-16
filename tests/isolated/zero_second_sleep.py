import eventlet

eventlet.sleep(0)
eventlet.monkey_patch()

from eventlet.hubs import get_hub
import time

FAILURES = []


def zero_second_sleep():
    try:
        eventlet.sleep(0)
        time.sleep(0)
    except RuntimeError:
        FAILURES.append(1)
        raise


# Simulate sleep(0) being called from a trampoline function. Or try to, anyway,
# not really sure if this matches the original reported bug but it does at
# least trigger the RuntimeError about blocking functions lacking the fix for
# sleep(0).
get_hub().schedule_call_local(0, zero_second_sleep)
zero_second_sleep()

if FAILURES:
    raise RuntimeError("There were failures")

print("pass")
