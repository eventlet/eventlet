import eventlet
from eventlet import hubs
from eventlet.green import select, socket
import time
import tests
original_socket = eventlet.patcher.original('socket')


def test_select_mark_file_as_reopened():
    # https://github.com/eventlet/eventlet/pull/294
    # Fix API inconsistency in select and Hub.
    # mark_as_closed takes one argument, but called without arguments.
    # on_error takes file descriptor, but called with an exception object.
    s = original_socket.socket()
    s.setblocking(0)
    s.bind(('127.0.0.1', 0))
    s.listen(5)

    gt = eventlet.spawn(select.select, [s], [s], [s])
    eventlet.sleep(0.01)

    with eventlet.Timeout(0.5) as t:
        with tests.assert_raises(hubs.IOClosed):
            hubs.get_hub().mark_as_reopened(s.fileno())
            gt.wait()
        t.cancel()


def test_select_read_and_write():
    # https://github.com/eventlet/eventlet/issues/551
    # Two related issues here:
    # - green.select only returns read or write flag, never both
    #   (even if both should apply) -- this is inconsistent with
    #   behavior of original select function
    # - spurious wakeup occurs after using select.select to check
    #   for both read and write, i.e. the next time the greenthread
    #   waits for something else
    sd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sd.bind(('127.0.0.1', 0))
    addr = sd.getsockname()
    sd.sendto(b'test', addr)

    select.select([sd], [], [])
    r, w, __ = select.select([sd], [sd], [], 0)
    def check_both_flags_returned():
        assert r and w
    yield check_both_flags_returned

    def check_sleep():
        now = time.time()
        eventlet.sleep(2)
        elapsed = time.time() - now

        assert elapsed > 1.0
    yield check_sleep
