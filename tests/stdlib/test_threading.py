from eventlet import patcher
from eventlet.green import threading
from eventlet.green import thread
from eventlet.green import time

# *NOTE: doesn't test as much of the threading api as we'd like because many of
# the tests are launched via subprocess and therefore don't get patched

patcher.inject('test.test_threading',
    globals(),
    ('threading', threading),
    ('thread', thread),
    ('time', time))

# "PyThreadState_SetAsyncExc() is a CPython-only gimmick, not (currently)
# exposed at the Python level.  This test relies on ctypes to get at it."
# Therefore it's also disabled when testing eventlet, as it's not emulated.
try:
    ThreadTests.test_PyThreadState_SetAsyncExc = lambda s: None
except (AttributeError, NameError):
    pass


if __name__ == "__main__":
    test_main()