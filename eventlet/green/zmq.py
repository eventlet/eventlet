"""The :mod:`zmq` module wraps the :class:`Socket` and :class:`Context` found in :mod:`pyzmq <zmq>` to be non blocking
"""
__zmq__ = __import__('zmq')
from eventlet import sleep, hubs
from eventlet.hubs import trampoline, _threadlocal
from eventlet.patcher import slurp_properties
from eventlet.support import greenlets as greenlet

__patched__ = ['Context', 'Socket']
slurp_properties(__zmq__, globals(), ignore=__patched__)

from collections import deque

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


# see http://api.zeromq.org/2-1:zmq-socket for explanation of socket types
_multi_reader_types = set([__zmq__.XREP, __zmq__.XREQ, __zmq__.SUB, __zmq__.PULL, __zmq__.PAIR])
_multi_writer_types = set([__zmq__.XREP, __zmq__.XREQ, __zmq__.PUB, __zmq__.PUSH, __zmq__.PAIR])

class Socket(__zmq__.Socket):
    """Green version of :class:`zmq.core.socket.Socket

    The following two methods are always overridden:
        * send
        * recv
    To ensure that the ``zmq.NOBLOCK`` flag is set and that sending or recieving
    is deferred to the hub (using :func:`eventlet.hubs.trampoline`) if a
    ``zmq.EAGAIN`` (retry) error is raised

    For some socket types, where multiple greenthreads could be
    calling send or recv at the same time, these methods are also
    overridden:
        * send_multipart
        * recv_multipart

    """

    def __init__(self, *args, **kwargs):
        super(Socket, self).__init__(*args, **kwargs)

        if False and self.socket_type in _multi_writer_types:
            # support multiple greenthreads writing at the same time
            self._writers = deque()
            self.send = self._xsafe_send
            self.send_multipart = self._xsafe_send_multipart

        if False and self.socket_type in _multi_reader_types:
            # support multiple greenthreads reading at the same time
            self._readers = deque()
            self.recv = self._xsafe_recv
            self.recv_multipart = self._xsafe_recv_multipart

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

    def _xsafe_send(self, msg, flags=0, copy=True, track=False):
        """
        A send method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            super(Socket, self).send(msg, flags=flags, track=track, copy=copy)
            return

        flags |= __zmq__.NOBLOCK

        if self._writers:
            self._writers.append((msg, flags, copy, track, greenlet.getcurrent()))
            if hubs.get_hub().switch():
                # msg was sent by another greenthread
                return
            else:
                pass
        else:
            self._writers.append((msg, flags, copy, track, greenlet.getcurrent()))

        while True:
            try:
                if (self.getsockopt(__zmq__.EVENTS) & __zmq__.POLLOUT):
                    super(Socket, self).send(msg, flags=flags, track=track,
                                             copy=copy)

                

                self._sock_wait(write=True)
                super(Socket, self).send(msg, flags=flags, track=track,
                                         copy=copy)
                return
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise

    def _xsafe_send_multipart(self, msg_parts, flags=0, copy=True, track=False):
        """
        A send_multipart method that's safe to use when multiple
        greenthreads are calling send, send_multipart, recv and
        recv_multipart on the same socket.

        Ensure multipart messages are not interleaved.
        """

        self._writers.append((list(reversed(msg)), flags, copy, track, greenlet.getcurrent()))
        if len(self._writers) == 1:
            # no blocked writers
            
            pass


    def _send_queued(self, ):
        """
        Send as many msgs from the writers deque as possible. Wake up
        the greenthreads for messages that are sent.
        """
        writers = self.writers
        hub = hubs.get_hub()

        while writers:
            msg, flags, copy, track, writer = writers[0]
            
            if isinstance(msg, list):
                is_list = True
                m = msg[-1]
            else:
                is_list = False
                m = msg
            try:
                super(Socket, self).send(m, flags=flags, track=track,
                                         copy=copy)
                hub.schedule_call_global(0, writer.switch, True)
            except (SystemExit, KeyboardInterrupt):
                raise
            except __zmq__.ZMQError, e:
                if e.errno == EAGAIN:
                    
                    pass
                else:
                    hub.schedule_call_global(0, writer.throw, e)


    def _xsafe_recv(self, flags=0, copy=True, track=False):
        """
        A recv method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        pass


    def _xsafe_recv_multipart(self, flags=0, copy=True, track=False):
        """
        A recv method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        pass
