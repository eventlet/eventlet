import os

import eventlet
from eventlet import hubs
from eventlet.green import select
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


def test_select_timeout_zero_unread_fd_returns_immediately():
    r, w = os.pipe()
    try:
        with eventlet.Timeout(0.5):
            result = select.select([r], [], [], 0.0)
        assert result == ([], [], [])
    finally:
        os.close(r)
        os.close(w)


def test_select_positive_timeout_yields_to_other_greenthreads():
    r, w = os.pipe()
    writer = eventlet.spawn(os.write, w, b'x')
    try:
        with eventlet.Timeout(1):
            assert select.select([r], [], [], 0.5) == ([r], [], [])
            assert writer.wait() == 1
    finally:
        writer.kill()
        os.close(r)
        os.close(w)


def test_select_timeout_zero_does_not_hang_if_timer_fires_early():
    # https://github.com/eventlet/eventlet/issues/798
    # If the 0-timeout hub timer expires before select reaches hub.switch(),
    # the greenthread used to wait forever. Simulate that race with a short
    # delay before the first switch.
    hub = hubs.get_hub()
    orig_switch = hub.switch
    first = [True]

    def delayed_switch():
        if first[0]:
            first[0] = False
            eventlet.sleep(0.01)
        return orig_switch()

    hub.switch = delayed_switch
    r, w = os.pipe()
    try:
        try:
            with eventlet.Timeout(0.5):
                result = select.select([r], [], [], 0.0)
        except eventlet.Timeout:
            raise AssertionError(
                'select(timeout=0) hung after the 0-timeout timer fired early'
            )
        assert result == ([], [], [])
    finally:
        hub.switch = orig_switch
        os.close(r)
        os.close(w)
