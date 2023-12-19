# https://github.com/eventlet/eventlet/issues/730
# https://github.com/eventlet/eventlet/pull/754
__test__ = False


if __name__ == "__main__":
    import logging
    import threading

    handler = logging.Handler()
    logger = logging.Logger("test")
    logger.addHandler(handler)

    # Initially these are standard Python RLocks:
    assert not isinstance(logging._lock, threading._PyRLock)
    assert not isinstance(handler.lock, threading._PyRLock)

    # After patching, they get converted:
    import eventlet.patcher
    eventlet.patcher.monkey_patch(thread=True)
    assert isinstance(logging._lock, threading._PyRLock)
    assert isinstance(handler.lock, threading._PyRLock)

    print("pass")
