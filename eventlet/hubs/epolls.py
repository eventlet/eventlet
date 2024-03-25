import errno
import warnings

from eventlet import patcher, support
from eventlet.hubs import hub, poll
select = patcher.original('select')


def is_available():
    return hasattr(select, 'epoll')


# NOTE: we rely on the fact that the epoll flag constants
# are identical in value to the poll constants
class Hub(poll.Hub):
    """
    .. warning::
        The eventlet epolls hub is now deprecated and will be removed.
        Users should begin planning a migration from eventlet to asyncio.
        Users are encouraged to switch to the eventlet asyncio hub in
        order to start this migration.
        Please find more details at https://eventlet.readthedocs.io/en/latest/migration.html
    """
    def __init__(self, clock=None):
        super().__init__(clock=clock)
        self.poll = select.epoll()

        warnings.warn(
            """
            ACTION REQUIRED: The eventlet epolls hub is now deprecated and will be removed.
            Users should begin planning a migration from eventlet to asyncio.
            Users are encouraged to switch to the eventlet asyncio hub in
            order to start this migration.
            Please find more details at https://eventlet.readthedocs.io/en/latest/migration.html
            """,
            DeprecationWarning,
        )

    def add(self, evtype, fileno, cb, tb, mac):
        oldlisteners = bool(self.listeners[self.READ].get(fileno) or
                            self.listeners[self.WRITE].get(fileno))
        # not super() to avoid double register()
        listener = hub.BaseHub.add(self, evtype, fileno, cb, tb, mac)
        try:
            self.register(fileno, new=not oldlisteners)
        except OSError as ex:    # ignore EEXIST, #80
            if support.get_errno(ex) != errno.EEXIST:
                raise
        return listener

    def do_poll(self, seconds):
        return self.poll.poll(seconds)
