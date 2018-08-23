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

    def wait(self, secs=None):
        readers = self.listeners[READ]
        writers = self.listeners[WRITE]
        if not readers and not writers:
            return
        if secs is not None:
            ev_sleep(secs)
            if not readers and not writers:
                return
            secs = 0

        for fd in readers:
            try:
                r, w, er = select.select([fd], [], [fd], secs)
                secs = 0
                try:
                    if er:
                        readers[fd].cb(fd)
                    elif r:
                        readers[fd].cb(fd)
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
                r, w, er = select.select([], [fd], [fd], secs)
                secs = 0
                try:
                    if er:
                        writers[fd].cb(fd)
                    elif w:
                        writers[fd].cb(fd)
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
