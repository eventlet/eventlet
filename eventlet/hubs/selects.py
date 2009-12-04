import sys
import select
import errno
import time

from eventlet.hubs.hub import BaseHub, READ, WRITE

try:
    BAD_SOCK = (errno.EBADF, errno.WSAENOTSOCK)
except AttributeError:
    BAD_SOCK = (errno.EBADF,)

class Hub(BaseHub):
    def _remove_closed_fds(self):
        """ Iterate through fds that have had their socket objects recently closed,
        removing the ones that are actually closed per the operating system.
        """
        for fd in self.closed_fds:
            try:
                select.select([fd], [], [], 0)
            except select.error, e:
                if e.args[0] == errno.EBADF:
                    self.remove_descriptor(fd)

    def wait(self, seconds=None):
        readers = self.listeners[READ]
        writers = self.listeners[WRITE]
        if not readers and not writers:
            if seconds:
                time.sleep(seconds)
            return
        try:
            r, w, er = select.select(readers.keys(), writers.keys(), readers.keys() + writers.keys(), seconds)
            self.closed_fds = []
        except select.error, e:
            if e.args[0] == errno.EINTR:
                return
            elif e.args[0] in BAD_SOCK:
                self._remove_closed_fds()
                self.closed_fds = []
                return
            else:
                raise

        for fileno in er:
            for r in readers.get(fileno):
                r(fileno)
            for w in writers.get(fileno):
                w(fileno)
            
        for listeners, events in ((readers, r), (writers, w)):
            for fileno in events:
                try:
                    l_list = listeners[fileno]
                    if l_list:
                        l_list[0](fileno)
                except self.SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
