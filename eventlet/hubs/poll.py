import errno
import sys

from eventlet.hubs.hub import BaseHub, noop, clear_sys_exc_info
from eventlet.support import get_errno
from eventlet import patcher

ev_sleep = patcher.original('time').sleep
select = patcher.original('select')

EXC_MASK = select.POLLERR | select.POLLHUP
READ_MASK = select.POLLIN | select.POLLPRI
WRITE_MASK = select.POLLOUT


class Hub(BaseHub):
    def __init__(self, clock=None):
        super(Hub, self).__init__(clock)
        self.poll = select.poll()

    def add(self, evtype, fileno, cb, tb, mac):
        listener = super(Hub, self).add(evtype, fileno, cb, tb, mac)
        self.register(fileno, new=True)
        return listener

    def remove(self, listener):
        super(Hub, self).remove(listener)
        self.register(listener.fileno)

    def register(self, fileno, new=False):
        mask = 0
        if self.listeners_r.get(fileno):
            mask |= READ_MASK | EXC_MASK
        if self.listeners_w.get(fileno):
            mask |= WRITE_MASK | EXC_MASK
        try:
            if mask:
                if new:
                    self.poll.register(fileno, mask)
                    return
                try:
                    self.poll.modify(fileno, mask)
                except (IOError, OSError):
                    self.poll.register(fileno, mask)
                return
            try:
                self.poll.unregister(fileno)
            except (KeyError, IOError, OSError):
                # raised if we try to remove a fileno that was
                # already removed/invalid
                pass
        except ValueError:
            # fileno is bad, issue 74
            self.remove_descriptor(fileno)
            raise

    def remove_descriptor(self, fileno):
        super(Hub, self).remove_descriptor(fileno)
        try:
            self.poll.unregister(fileno)
        except (KeyError, ValueError, IOError, OSError):
            # raised if we try to remove a fileno that was
            # already removed/invalid
            pass

    def do_poll(self, seconds):
        # poll.poll expects integral milliseconds
        return self.poll.poll(int(seconds * 1000.0))

    def wait(self, seconds=None):

        if not self.listeners_r and not self.listeners_w:
            if seconds is not None:
                ev_sleep(seconds)
                if not self.listeners_r and not self.listeners_w:
                    return
                seconds = 0
            else:
                return

        try:
            presult = self.do_poll(seconds)
        except (IOError, select.error) as e:
            if get_errno(e) == errno.EINTR:
                return
            raise

        if self.debug_blocking:
            self.block_detect_pre()

        # Accumulate the listeners to call back to prior to
        # triggering any of them. This is to keep the set
        # of callbacks in sync with the events we've just
        # polled for. It prevents one handler from invalidating
        # another.
        # Invalidating can happen only follow a next call to wait with new set of p_result, ain't?

        callbacks = set()
        for fileno, event in presult:
            if event & READ_MASK:
                callbacks.add((self.listeners_r.get(fileno, noop), fileno))
            if event & WRITE_MASK:
                callbacks.add((self.listeners_w.get(fileno, noop), fileno))
            if event & select.POLLNVAL:
                self.remove_descriptor(fileno)
                continue
            if event & EXC_MASK:
                callbacks.add((self.listeners_r.get(fileno, noop), fileno))
                callbacks.add((self.listeners_w.get(fileno, noop), fileno))

        for listener, fileno in callbacks:
            try:
                listener.cb(fileno)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fileno, sys.exc_info())
                clear_sys_exc_info()

        if self.debug_blocking:
            self.block_detect_post()
