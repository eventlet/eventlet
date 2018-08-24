import errno
import sys
from eventlet import patcher
from eventlet.support import get_errno, clear_sys_exc_info
select = patcher.original('select')
ev_sleep = patcher.original('time').sleep

from eventlet.hubs.hub import BaseHub, READ, WRITE, noop

try:
    BAD_SOCK = set((errno.EBADF, errno.WSAENOTSOCK))
except AttributeError:
    BAD_SOCK = set((errno.EBADF,))


class Hub(BaseHub):
    def _remove_bad_fds(self):
        """ Iterate through fds, removing the ones that are bad per the
        operating system.
        """
        for fd in list(self.listeners[READ]) + list(self.listeners[WRITE]):
            try:
                select.select([fd], [], [], 0)
            except select.error as e:
                if get_errno(e) in BAD_SOCK:
                    self.remove_descriptor(fd)

    def wait(self, seconds=None):
        readers = self.listeners[READ]
        writers = self.listeners[WRITE]
        if not readers and not writers:
            return
        if seconds is not None:
            ev_sleep(seconds)
            if not readers and not writers:
                return
            seconds = 0

        for fd in readers:
            try:
                r, w, er = select.select([fd], [], [fd], seconds)
                seconds = 0
                try:
                    if r or er:
                        readers.get(fd, noop).cb(fd)  # in-case, fd no longer exists
                except self.SYSTEM_EXCEPTIONS:
                    continue
                except:
                    self.squelch_exception(fd, sys.exc_info())
                    clear_sys_exc_info()

            except select.error as e:
                if get_errno(e) == errno.EINTR:
                    pass
                elif get_errno(e) in BAD_SOCK:
                    self.remove_descriptor(fd)
                else:
                    raise

        for fd in writers:
            try:
                r, w, er = select.select([], [fd], [fd], seconds)
                seconds = 0
                try:
                    if w or er:
                        writers.get(fd, noop).cb(fd)
                except self.SYSTEM_EXCEPTIONS:
                    continue
                except:
                    self.squelch_exception(fd, sys.exc_info())
                    clear_sys_exc_info()

            except select.error as e:
                if get_errno(e) == errno.EINTR:
                    pass
                elif get_errno(e) in BAD_SOCK:
                    self.remove_descriptor(fd)
                else:
                    raise
