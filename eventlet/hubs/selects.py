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
                ev_sleep(0.00001)
                if not self.listeners_r and not self.listeners_w:
                    return
                seconds = 0
            else:
                return

        try:
            rs, ws, er = select.select(self.listeners_r.keys(), self.listeners_w.keys(),
                                       list(self.listeners_r.keys()) + list(self.listeners_w.keys()),
                                       seconds)
        except select.error as e:
            if get_errno(e) == errno.EINTR:
                return
            elif get_errno(e) in BAD_SOCK:
                self._remove_bad_fds()
                return
            else:
                raise

        for fileno in er:
            r = self.listeners_r.get(fileno)
            w = self.listeners_w.get(fileno)
            try:
                if r:
                    r.cb(fileno)
                if w:
                    w.cb(fileno)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fileno, sys.exc_info())
                clear_sys_exc_info()

        for fileno in rs:
            r = self.listeners_r.get(fileno)
            if not r:
                continue
            try:
                r.cb(fileno)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fileno, sys.exc_info())
                clear_sys_exc_info()

        for fileno in ws:
            w = self.listeners_w.get(fileno)
            if not w:
                continue
            try:
                w.cb(fileno)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fileno, sys.exc_info())
                clear_sys_exc_info()
