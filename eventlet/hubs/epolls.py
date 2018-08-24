import errno
from eventlet.support import get_errno
from eventlet import patcher
select = patcher.original('select')
if not hasattr(select, 'epoll'):
    # TODO: remove mention of python-epoll on 2019-01
    raise ImportError('No epoll implementation found in select module.'
                      ' python-epoll (or similar) package support was removed,'
                      ' please open issue on https://github.com/eventlet/eventlet/'
                      ' if you must use epoll outside stdlib.')
epoll = select.epoll

from eventlet.hubs.hub import BaseHub
from eventlet.hubs import poll

# NOTE: we rely on the fact that the epoll flag constants
# are identical in value to the poll constants


class Hub(poll.Hub):
    def __init__(self, clock=None):
        BaseHub.__init__(self, clock)
        self.poll = epoll()

    def add(self, evtype, fileno, cb, tb, mac):
        not_new = not(fileno in self.listeners_r or fileno in self.listeners_w)
        listener = BaseHub.add(self, evtype, fileno, cb, tb, mac)
        try:
            # new=True, Means we've added a new listener
            self.register(fileno, new=not_new)

        except IOError as ex:    # ignore EEXIST, #80
            if get_errno(ex) != errno.EEXIST:
                raise
        return listener

    def do_poll(self, seconds):
        return self.poll.poll(seconds)
