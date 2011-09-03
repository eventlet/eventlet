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

_disable_send_types = set([__zmq__.SUB, __zmq__.PULL])
_disable_recv_types = set([__zmq__.PUB, __zmq__.PUSH])


# TODO: 
# - Ensure that recv* and send* methods raise error when called on a
#   closed socket. They should not block.
# - Return correct message tracker from send* methods
# - Make MessageTracker.wait zmq friendly

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

    def __init__(self, context, socket_type):
        super(Socket, self).__init__(context, socket_type)

        self._writers = None
        self._readers = None
        # customize send and recv functions based on socket type
        if socket_type in _multi_writer_types:
            # support multiple greenthreads writing at the same time
            self._writers = deque()
            self.send = self._xsafe_send
            self.send_multipart = self._xsafe_send_multipart
        elif socket_type in _disable_send_types:
            self.send = self.send_multipart = self._send_not_supported

        if socket_type in _multi_reader_types:
            # support multiple greenthreads reading at the same time
            self._readers = deque()
            self.recv = self._xsafe_recv
            self.recv_multipart = self._xsafe_recv_multipart
        elif socket_type in _disable_recv_types:
            self.recv = self.recv_multipart = self._recv_not_supported

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
            super(Socket, self).send(msg, flags=flags, copy=copy, track=track)
            return

        flags |= __zmq__.NOBLOCK

        while True:
            try:
                self._sock_wait(write=True)
                return super(Socket, self).send(msg, flags=flags, copy=copy, track=track)
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
            return super(Socket, self).recv(flags=flags, copy=copy, track=track)

        flags |= __zmq__.NOBLOCK

        while True:
            try:
                self._sock_wait(read=True)
                return super(Socket, self).recv(flags=flags, copy=copy, track=track)
            except __zmq__.ZMQError, e:
                if e.errno != EAGAIN:
                    raise

    def _send_not_supported(self, msg, flags=0, copy=True, track=False):
        raise __zmq__.ZMQError(__zmq__.ENOTSUP)

    def _recv_not_supported(self, flags=0, copy=True, track=False):
        raise __zmq__.ZMQError(__zmq__.ENOTSUP)


    def _xsafe_sock_wait(self, read=False, write=False):
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


    def _xsafe_send(self, msg, flags=0, copy=True, track=False):
        """
        A send method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).send(msg, flags=flags, copy=copy, track=track)

        self._xsafe_inner_send(msg, flags, copy, track)
   
    def _xsafe_send_multipart(self, msg_parts, flags=0, copy=True, track=False):
        """
        A send_multipart method that's safe to use when multiple
        greenthreads are calling send, send_multipart, recv and
        recv_multipart on the same socket.

        Ensure multipart messages are not interleaved.
        """

        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).send_multipart(msg_parts, flags=flags, copy=copy, track=track)

        self._xsafe_inner_send(list(msg_parts), flags, copy, track)

    def _xsafe_inner_send(self, msg, flags, copy, track):
        is_listening = bool(self._writers or self._readers)

        self._writers.append((greenlet.getcurrent(), msg, flags | __zmq__.NOBLOCK, copy, track))
        if is_listening:
            # Other readers or writers are blocked. If this is the
            # first writer, it may be possible to send immediately
            if len(self._writers) == 1:
                # TODO: Check EVENTS first?
                result = self._send_queued()
                if not self._writers:
                    # success!
                    return result
            
            # other readers or writers are blocked so this greenthread must wait its turn
            result = hubs.get_hub().switch()
            if result is False:
                # msg was not yet sent, but this thread was woken up
                # so that it could process the queues
                return self._process_queues()
            else:
                # msg was sent by another greenthread
                return result
        else:
            return self._process_queues()

    def _xsafe_recv(self, flags=0, copy=True, track=False):
        """
        A recv method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """

        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).recv(flags=flags, copy=copy, track=track)

        return self._xsafe_inner_recv(False, flags, copy, track)

    def _xsafe_recv_multipart(self, flags=0, copy=True, track=False):
        """
        A recv method that's safe to use when multiple greenthreads
        are calling send, send_multipart, recv and recv_multipart on
        the same socket.
        """
        if flags & __zmq__.NOBLOCK:
            return super(Socket, self).recv_multipart(flags=flags, copy=copy, track=track)

        return self._xsafe_inner_recv(True, flags, copy, track)

    def _xsafe_inner_recv(self, multi, flags, copy, track):
        is_listening = bool(self._writers or self._readers)

        self._readers.append((greenlet.getcurrent(), multi, flags | __zmq__.NOBLOCK, copy, track))

        if is_listening:
            # Other readers or writers are blocked. If this is the
            # first reader, it may be possible to recv immediately
            if len(self._readers) == 1:
                # TODO: Check EVENTS first?
                result = self._recv_queued()
                if not self._readers:
                    # success!
                    return result
            
            # other readers or writers are blocked so this greenthread must wait its turn
            result = hubs.get_hub().switch()
            if result is False:
                # msg was not yet received, but this thread was woken up
                # so that it could process the queues
                return self._process_queues()
            else:
                # msg was received
                return result
        else:
            return self._process_queues()


    def _process_queues(self):
        """ If there are readers or writers queued, this method tries
        to recv or send messages and ensures processing continues
        either in this greenthread or in another one. """
        readers = self._readers
        writers = self._writers

        send_result = None
        recv_result = None
        while True:
            events = self.getsockopt(__zmq__.EVENTS)
            try:
                if readers and (events & __zmq__.POLLIN):
                    recv_result = self._recv_queued()

                if writers and (events & __zmq__.POLLOUT):
                    send_result = self._send_queued()
            except (SystemExit, KeyboardInterrupt):
                raise
            except:
                # an error occurred for this greenthread's send/recv
                # call. Wake another thread to continue processing.
                if readers:
                    hubs.get_hub().schedule_call_global(0, readers[0][0].switch, False)
                elif writers:
                    hubs.get_hub().schedule_call_global(0, writers[0][0].switch, False)
                raise

            # send and recv cannot continue right now. If there are
            # more readers or writers queued, either trampoline or
            # wake another greenthread.
            current = greenlet.getcurrent()
            if (readers and readers[0][0] is current) or (writers and writers[0][0] is current):
                # Only trampoline if this thread is the next reader or writer,
                # and ONLY trampoline on read events for zmq FDs.
                trampoline(self.getsockopt(__zmq__.FD), read=True)
            else:
                if readers:
                    hubs.get_hub().schedule_call_global(0, readers[0][0].switch, False)
                elif writers:
                    hubs.get_hub().schedule_call_global(0, writers[0][0].switch, False)
                return send_result or recv_result
                

    def _send_queued(self):
        """
        Send as many msgs from the writers deque as possible. Wake up
        the greenthreads for messages that are sent.
        """
        writers = self._writers
        current = greenlet.getcurrent()
        hub = hubs.get_hub()
        super_send = super(Socket, self).send
        super_send_multipart = super(Socket, self).send_multipart

        result = None

        while writers:
            writer, msg, flags, copy, track = writers[0]
            try:
                if isinstance(msg, list):
                    r = super_send_multipart(msg, flags=flags, copy=copy, track=track)
                else:
                    r = super_send(msg, flags=flags, copy=copy, track=track)

                # remember this thread's result
                if current is writer:
                    result = r
            except (SystemExit, KeyboardInterrupt):
                raise
            except __zmq__.ZMQError, e:
                if e.errno == EAGAIN:
                    return result
                else:
                    # message failed to send
                    writers.popleft()
                    if current is writer:
                        raise
                    else:
                        hub.schedule_call_global(0, writer.throw, e)
                        continue

            # move to the next msg
            writers.popleft()
            # wake writer
            if current is not writer:
                hub.schedule_call_global(0, writer.switch, r)
        return result


    def _recv_queued(self):
        """
        Recv as many msgs for each of the greenthreads in the readers
        deque. Wakes up the greenthreads for messages that are
        received. If the received message is for the current
        greenthread, returns immediately.
        """
        readers = self._readers
        super_recv = super(Socket, self).recv
        super_recv_multipart = super(Socket, self).recv_multipart

        current = greenlet.getcurrent()
        hub = hubs.get_hub()

        while readers:
            reader, multi, flags, copy, track = readers[0]
            try:
                if multi:
                    msg = super_recv_multipart(flags, copy, track)
                else:
                    msg = super_recv(flags, copy, track)

            except (SystemExit, KeyboardInterrupt):
                raise
            except __zmq__.ZMQError, e:
                if e.errno == EAGAIN:
                    return None
                else:
                    # message failed to send
                    readers.popleft()
                    if current is reader:
                        raise
                    else:
                        hub.schedule_call_global(0, reader.throw, e)
                        continue

            # move to the next reader
            readers.popleft()

            if current is reader:
                return msg
            else:
                hub.schedule_call_global(0, reader.switch, msg)

        return None
