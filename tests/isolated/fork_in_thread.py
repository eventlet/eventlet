import eventlet

eventlet.monkey_patch()

import os
import time
import threading

results = []
parent = True


def check_current():
    if threading.current_thread() not in threading.enumerate():
        raise SystemExit(17)


def background():
    time.sleep(1)
    check_current()
    results.append(True)


def forker():
    pid = os.fork()
    check_current()
    if pid != 0:
        # We're in the parent. Wait for child to die.
        wait_pid, status = os.wait()
        exit_code = os.waitstatus_to_exitcode(status)
        assert wait_pid == pid
        assert exit_code == 0, exit_code
    else:
        global parent
        parent = False
    results.append(True)


t = threading.Thread(target=background)
t.start()
t2 = threading.Thread(target=forker)
t2.start()
t2.join()
t.join()

check_current()
assert results == [True, True]
if parent:
    print("pass")
