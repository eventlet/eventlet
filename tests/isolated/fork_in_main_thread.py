import eventlet

eventlet.monkey_patch()

import os
import time
import threading

results = set()
parent = True


def check_current():
    if threading.current_thread() not in threading.enumerate():
        raise SystemExit(17)


def background():
    time.sleep(1)
    check_current()
    results.add("background")


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
    results.add("forker")


t = threading.Thread(target=background)
t.start()
forker()
t.join()

check_current()
assert results == {"background", "forker"}, results
if parent:
    print("pass")
