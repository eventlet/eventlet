import eventlet
import eventlet.patcher

eventlet.monkey_patch()

threading_orig = eventlet.patcher.original("threading")

EVENTS = []


def os_thread_2():
    eventlet.sleep(0.1)
    EVENTS.append(2)
    eventlet.sleep(0.1)
    EVENTS.append(2)


threading_orig.Thread(target=os_thread_2).start()
EVENTS.append(1)
eventlet.sleep(0.05)
EVENTS.append(1)
eventlet.sleep(0.4)
EVENTS.append(3)
if EVENTS == [1, 1, 2, 2, 3]:
    print("pass")
