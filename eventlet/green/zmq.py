"""The :mod:`zmq` module wraps the :class:`Socket` and :class:`Context` found in :mod:`pyzmq <zmq>` to be non blocking
"""
__zmq__ = __import__('zmq')
from eventlet import sleep
from eventlet.hubs import trampoline, _threadlocal
from eventlet.patcher import slurp_properties

__patched__ = ['Context', 'Socket']
slurp_properties(__zmq__, globals(), ignore=__patched__)


def Context(io_threads=1):
    """Factory function replacement for :class:`zmq.core.context.Context`

    This factory ensures the :class:`zeromq hub <eventlet.hubs.zeromq.Hub>`
    is the active hub, and defers creation (or retreival) of the ``Context``
    to the hub's :meth:`~eventlet.hubs.zeromq.Hub.get_context` method
    
    It's a factory function due to the fact that there can only be one :class:`_Context`
    instance per thread. This is due to the way :class:`zmq.core.poll.Poller`
    works
    """
    try:
        return _threadlocal.context
    except AttributeError:
        _threadlocal.context = _Context(io_threads)
        return _threadlocal.context

class _Context(__zmq__.Context):
    """Internal subclass of :class:`zmq.core.context.Context`

    .. warning:: Do not grab one of these yourself, use the factory function
        :func:`eventlet.green.zmq.Context`
    """

    def socket(self, socket_type):
        """Overridden method to ensure that the green version of socket is used

        Behaves the same as :meth:`zmq.core.context.Context.socket`, but ensures
        that a :class:`Socket` with all of its send and recv methods set to be
        non-blocking is returned
        """
        return Socket(self, socket_type)

class Socket(__zmq__.Socket):
    """Green version of :class:`zmq.core.socket.Socket

    The following four methods are overridden:

        * _send_message
        * _send_copy
        * _recv_message
        * _recv_copy

    To ensure that the ``zmq.NOBLOCK`` flag is set and that sending or recieving
    is deferred to the hub (using :func:`eventlet.hubs.trampoline`) if a
    ``zmq.EAGAIN`` (retry) error is raised
    """

    def _sock_wait(self, read=False, write=False):
        """
        First checks if there are events in the socket, to avoid
        edge trigger problems with race conditions.  Then if there
        are none it will trampoline and when coming back check
        for the events.
        """
        events = self.getsockopt(__zmq__.EVENTS)

        if read and (events & __zmq__.POLLIN):
            return events
        elif write and (events & __zmq__.POLLOUT):
            return events
        else:
            # ONLY trampoline on read events for the zmq FD
            trampoline(self.getsockopt(__zmq__.FD), read=True)
            return self.getsockopt(__zmq__.EVENTS)

    def send(self, msg, flags=0, copy=True, track=False):
        """
        Override this instead of the internal _send_* methods 
        since those change and it's not clear when/how they're
        called in real code.
        """
        if flags & __zmq__.NOBLOCK:
            super(Socket, self).send(msg, flags=flags, track=track, copy=copy)
            return

        flags |= __zmq__.NOBLOCK

        while True:
            try:
                self._sock_wait(write=True)
                super(Socket, self).send(msg, flags=flags, track=track,
                                         copy=copy)
                return
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise

    def recv(self, flags=0, copy=True, track=False):
        """
        Override this instead of the internal _recv_* methods 
        since those change and it's not clear when/how they're
        called in real code.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).recv(flags=flags, track=track, copy=copy)

        flags |= __zmq__.NOBLOCK

        while True:
            try:
                self._sock_wait(read=True)
                m = super(Socket, self).recv(flags=flags, track=track, copy=copy)
                if m is not None:
                    return m
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise


