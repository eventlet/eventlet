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
from types import MethodType

class _QueueLock(object):
    """A Lock that can be acquired by at most one thread. Any other
    thread calling acquire will be blocked in a queue. When release
    is called, the threads are awoken in the order they blocked,
    one at a time. This lock can be required recursively by the same
    thread."""
    def __init__(self):
        self._waiters = deque()
        self._count = 0
        self._holder = None

    def __nonzero__(self):
        return self._count

    def __enter__(self):
        self.acquire()
        
    def __exit__(self, type, value, traceback):
        self.release()

    def acquire(self):
        current = greenlet.getcurrent()
        if (self._waiters or self._count > 0) and self._holder is not current:
            # block until lock is free
            self._waiters.append(current)
            hubs.get_hub().switch()
            w = self._waiters.popleft()

            assert w is current, 'Waiting threads woken out of order'
            assert self._count == 0, 'After waking a thread, the lock must be unacquired'

        self._holder = current
        self._count += 1

    def release(self):
        assert self._count > 0, 'Cannot release unacquired lock'

        self._count -= 1
        if self._count == 0:
            self._holder = None
            if self._waiters:
                # wake next
                hubs.get_hub().schedule_call_global(0, self._waiters[0].switch)
        
class _SimpleEvent(object):
    """Represents a possibly blocked thread which may be blocked
    inside this class' block method or inside a trampoline call. In
    either case, the threads can be awoken by calling wake(). Wake()
    can be called multiple times and all but the first call will have
    no effect."""

    def __init__(self):
        self._blocked_thread = None
        self._wakeupper = None

    def __nonzero__(self):
        return self._blocked_thread is not None

    def block(self):
        with self:
            hubs.get_hub().switch()

    def __enter__(self):
        assert self._blocked_thread is None, 'Cannot block more than one thread on one SimpleEvent'
        self._blocked_thread = greenlet.getcurrent()
        
    def __exit__(self, type, value, traceback):
        self._blocked_thread = None
        # cleanup the wakeup task
        if self._wakeupper is not None:
            # Important to cancel the wakeup task so it doesn't
            # spuriously wake this greenthread later on.
            self._wakeupper.cancel()
            self._wakeupper = None

    def wake(self):
        """Schedules the blocked thread to be awoken and return
        True. If wake has already been called or if there is no
        blocked thread, then this call has no effect and returns
        False."""
        if self._blocked_thread is not None and self._wakeupper is None:
            self._wakeupper = hubs.get_hub().schedule_call_global(0, self._blocked_thread.switch)
            return True
        return False

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


# TODO: 
# - Ensure that recv* and send* methods raise error when called on a
#   closed socket. They should not block.
# - Return correct message tracker from send* methods
# - Make MessageTracker.wait zmq friendly
# - What should happen to threads blocked on send/recv when socket is
#   closed?

def _wraps(source_fn):
    """A decorator that copies the __name__ and __doc__ from the given
    function
    """
    def wrapper(dest_fn):
        dest_fn.__name__ = source_fn.__name__
        dest_fn.__doc__ = source_fn.__doc__
        return dest_fn
    return wrapper

class Socket(__zmq__.Socket):
    """Green version of :class:`zmq.core.socket.Socket

    The following two methods are always overridden:
        * send
        * recv
        * getsockopt
    To ensure that the ``zmq.NOBLOCK`` flag is set and that sending or recieving
    is deferred to the hub (using :func:`eventlet.hubs.trampoline`) if a
    ``zmq.EAGAIN`` (retry) error is raised
    """

    def __init__(self, context, socket_type):
        super(Socket, self).__init__(context, socket_type)

        self._in_trampoline = False
        self._send_event = _SimpleEvent()
        self._recv_event = _SimpleEvent()

        # customize send and recv methods based on socket type
        ops = self._eventlet_ops.get(socket_type)
        if ops:
            self._send_lock = None
            self._recv_lock = None
            send, msend, recv, mrecv = ops
            if send:
                self._send_lock = _QueueLock()
                self.send = MethodType(send, self, Socket)
                self.send_multipart = MethodType(msend, self, Socket)
            else:
                self.send = self.send_multipart = self._send_not_supported

            if recv:
                self._recv_lock = _QueueLock()
                self.recv = MethodType(recv, self, Socket)
                self.recv_multipart = MethodType(mrecv, self, Socket)
            else:
                self.recv = self.recv_multipart = self._send_not_supported

    def _trampoline(self, is_send):
        """Wait for events on the zmq socket. After this method
        returns it is still possible that send and recv will return
        EAGAIN.

        This supports being called by two separate greenthreads, a
        sender and a receiver, but only the first caller will actually
        call eventlet's trampoline method. The second thread will
        still block. 
        """

        evt = self._send_event if is_send else self._recv_event
        if self._in_trampoline:
            # Already a thread blocked in trampoline.
            evt.block()
        else:
            try:
                self._in_trampoline = True
                with evt:
                    # Only trampoline on read events for zmq FDs, never write.
                    trampoline(self.getsockopt(__zmq__.FD), read=True)
            finally:
                self._in_trampoline = False

    @_wraps(__zmq__.Socket.send)
    def send(self, msg, flags=0, copy=True, track=False):
        """Send method used by REP and REQ sockets. The lock-step
        send->recv->send->recv restriction of these sockets makes this
        implementation simple.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).send(msg, flags, copy, track)

        flags |= __zmq__.NOBLOCK

        while True:
            try:
                return super(Socket, self).send(msg, flags, copy, track)
            except __zmq__.ZMQError, e:
                if e.errno == EAGAIN:
                    self._trampoline(True)
                else:
                    raise

    @_wraps(__zmq__.Socket.recv)
    def recv(self, flags=0, copy=True, track=False):
        """Recv method used by REP and REQ sockets. The lock-step
        send->recv->send->recv restriction of these sockets makes this
        implementation simple.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).recv(flags, copy, track)

        flags |= __zmq__.NOBLOCK

        while True:
            try:
                return super(Socket, self).recv(flags, copy, track)
            except __zmq__.ZMQError, e:
                if e.errno == EAGAIN:
                    self._trampoline(False)
                else:
                    raise

    @_wraps(__zmq__.Socket.getsockopt)
    def getsockopt(self, option):
        result = super(Socket, self).getsockopt(option)
        if option == __zmq__.EVENTS:
            # Getting the events causes the zmq socket to process
            # events which may mean a msg can be sent or received. If
            # there is a greenthread blocked and waiting for events,
            # it will miss the edge-triggered read event, so wake it
            # up.
            if self._send_evt and (result & __zmq__.POLLOUT):
                self._send_evt.wake()

            if self._recv_evt and (result & __zmq__.POLLIN):
                self._recv_evt.wake()
        return result

    def _send_not_supported(self, msg, flags, copy, track):
        raise __zmq__.ZMQError(__zmq__.ENOTSUP)

    def _recv_not_supported(self, flags, copy, track):
        raise __zmq__.ZMQError(__zmq__.ENOTSUP)

    @_wraps(__zmq__.Socket.send)
    def _xsafe_send(self, msg, flags=0, copy=True, track=False):
        """A send method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            result = super(Socket, self).send(msg, flags, copy, track)
            if self._send_event or self._recv_event:
                getsockopt(__zmq__.EVENTS) # triggers wakeups
            return result

        # TODO: pyzmq will copy the message buffer and create Message
        # objects under some circumstances. We could do that work here
        # once to avoid doing it every time the send is retried.
        flags |= __zmq__.NOBLOCK
        with self._send_lock:
            while True:
                try:
                    return super(Socket, self).send(msg, flags, copy, track)
                except __zmq__.ZMQError, e:
                    if e.errno == EAGAIN:
                        self._trampoline(True)
                    else:
                        raise
                finally:
                    # The call to send processes 0mq events and may
                    # make the socket ready to recv. Wake the next
                    # receiver. (Could check EVENTS for POLLIN here)
                    if self._recv_event:
                        self._recv_event.wake()


    @_wraps(__zmq__.Socket.send_multipart)
    def _xsafe_send_multipart(self, msg_parts, flags=0, copy=True, track=False):
        """A send_multipart method that's safe to use when multiple
        greenthreads are calling send, send_multipart, recv and
        recv_multipart on the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).send_multipart(msg_parts, flags, copy, track)

        # acquire lock here so the subsequent calls to send for the
        # message parts after the first don't block
        with self._send_lock:
            return super(Socket, self).send_multipart(msg_parts, flags, copy, track)

    @_wraps(__zmq__.Socket.recv)
    def _xsafe_recv(self, flags=0, copy=True, track=False):
        """A recv method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            msg = super(Socket, self).recv(flags, copy, track)
            if self._send_event or self._recv_event:
                getsockopt(__zmq__.EVENTS) # triggers wakeups
            return msg

        flags |= __zmq__.NOBLOCK
        with self._recv_lock:
            while True:
                try:
                    try:
                        return super(Socket, self).recv(flags, copy, track)
                    finally:
                        # The call to recv processes 0mq events and may
                        # make the socket ready to send. Wake the next
                        # receiver. (Could check EVENTS for POLLOUT here)
                        if self._send_event:
                            self._send_event.wake()
                except __zmq__.ZMQError, e:
                    if e.errno == EAGAIN:
                        self._trampoline(False)
                    else:
                        raise

    @_wraps(__zmq__.Socket.recv_multipart)
    def _xsafe_recv_multipart(self, flags=0, copy=True, track=False):
        """A recv_multipart method that's safe to use when multiple
        greenthreads are calling send, send_multipart, recv and
        recv_multipart on the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).recv_multipart(flags, copy, track)

        # acquire lock here so the subsequent calls to recv for the
        # message parts after the first don't block
        with self._recv_lock:
            return super(Socket, self).recv_multipart(flags, copy, track)              

    # The behavior of the send and recv methods depends on the socket
    # type. See http://api.zeromq.org/2-1:zmq-socket for explanation
    # of socket types. For the green Socket, our main concern is
    # supporting calling send or recv from multiple greenthreads when
    # it makes sense for the socket type.
    _send_only_ops = (_xsafe_send, _xsafe_send_multipart, None, None)
    _recv_only_ops = (None, None, _xsafe_recv, _xsafe_recv_multipart)
    _full_ops = (_xsafe_send, _xsafe_send_multipart, _xsafe_recv, _xsafe_recv_multipart)

    _eventlet_ops = {
        __zmq__.PUB: _send_only_ops,
        __zmq__.SUB: _recv_only_ops,

        __zmq__.PUSH: _send_only_ops,
        __zmq__.PULL: _recv_only_ops,

        __zmq__.PAIR: _full_ops
        }

    try:
        _eventlet_ops[__zmq__.XREP] = _full_ops
        _eventlet_ops[__zmq__.XREQ] = _full_ops
    except AttributeError:
        # XREP and XREQ are being renamed ROUTER and DEALER
        _eventlet_ops[__zmq__.ROUTER] = _full_ops
        _eventlet_ops[__zmq__.DEALER] = _full_ops
