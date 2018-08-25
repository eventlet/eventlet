import errno
import sys
from eventlet import patcher
from eventlet.support import get_errno, clear_sys_exc_info
from eventlet.hubs.hub import BaseHub, noop

select = patcher.original('select')
ev_sleep = patcher.original('time').sleep

try:
    BAD_SOCK = set((errno.EBADF, errno.WSAENOTSOCK))
except AttributeError:
    BAD_SOCK = set((errno.EBADF,))


class Hub(BaseHub):
    def _remove_bad_fds(self):
        """ Iterate through fds, removing the ones that are bad per the
        operating system.
        """
        for fd in list(self.listeners_r) + list(self.listeners_w):
            try:
                select.select([fd], [], [], 0)
            except select.error as e:
                if get_errno(e) in BAD_SOCK:
                    self.remove_descriptor(fd)

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
            r, w, er = select.select(self.listeners_r.keys(), self.listeners_w.keys(),
                                     list(self.listeners_r.keys())+list(self.listeners_w.keys()),
                                     seconds)
        except select.error as e:
            if get_errno(e) == errno.EINTR:
                return
            elif get_errno(e) in BAD_SOCK:
                self._remove_bad_fds()
                return
            else:
                raise

        for fd in er:
            try:
                if fd in self.listeners_r:
                    self.listeners_r.get(fd, noop).cb(fd)
                if fd in self.listeners_w:
                    self.listeners_w.get(fd, noop).cb(fd)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fd, sys.exc_info())
                clear_sys_exc_info()

        for fd in r:
            try:
                self.listeners_r.get(fd, noop).cb(fd)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fd, sys.exc_info())
                clear_sys_exc_info()

        for fd in w:
            try:
                self.listeners_w.get(fd, noop).cb(fd)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fd, sys.exc_info())
                clear_sys_exc_info()
