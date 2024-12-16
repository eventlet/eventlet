"""
Ensure pre-existing RLocks get upgraded in a variety of situations.
"""

import sys
import threading
import unittest.mock
import eventlet

python_lock = threading._PyRLock


class NS:
    lock = threading.RLock()

    class NS2:
        lock = threading.RLock()

    dict = {1: 2, 12: threading.RLock()}
    list = [0, threading.RLock()]


def ensure_upgraded(lock):
    if not isinstance(lock, python_lock):
        raise RuntimeError(lock)


if __name__ == '__main__':
    # These extra print()s caused either test failures or segfaults until
    # https://github.com/eventlet/eventlet/issues/864 was fixed.
    if sys.version_info[:2] > (3, 9):
        print(unittest.mock.NonCallableMock._lock)
    print(NS.lock)
    # unittest.mock imports asyncio, so clear out asyncio.
    for name in list(sys.modules.keys()):
        if name.startswith("asyncio"):
            del sys.modules[name]
    eventlet.monkey_patch()
    ensure_upgraded(NS.lock)
    ensure_upgraded(NS.NS2.lock)
    ensure_upgraded(NS.dict[12])
    ensure_upgraded(NS.list[1])
    if sys.version_info[:2] > (3, 9):
        ensure_upgraded(unittest.mock.NonCallableMock._lock)
    print("pass")
