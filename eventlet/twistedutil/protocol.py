"""Basic twisted protocols converted to synchronous mode"""
from twisted.internet.protocol import Protocol as twistedProtocol
from twisted.internet.error import ConnectionDone
from twisted.internet.protocol import Factory, _InstanceFactory
from twisted.internet import defer

from eventlet.api import spawn
from eventlet.coros import queue
from eventlet.twistedutil import block_on


class BaseBuffer(object):

    def build_protocol(self):
        # note to subclassers: self._queue must have send and send_exception that are non-blocking
        self.protocol = self.protocol_class()
        self._queue = self.protocol._queue = queue()
        return self.protocol
    
    def _wait(self):
        return self._queue.wait()
    
    @property
    def transport(self):
        return self.protocol.transport

    def __getattr__(self, item):
        return getattr(self.protocol.transport, item)


class Protocol(twistedProtocol):

    def dataReceived(self, data):
        self._queue.send(data)

    def connectionLost(self, reason):
        self._queue.send_exception(reason.type, reason.value, reason.tb)
        self._queue = None


class Unbuffered(BaseBuffer):

    protocol_class = Protocol

    def recv(self):
        """Receive a single chunk of undefined size.

        Return '' if connection was closed cleanly, raise the exception if it was closed
        in a non clean fashion. After that all successive calls return ''.

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Unbuffered).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> buf.recv()
        'you said hello. '
        >>> buf.recv()
        'BYE'
        >>> buf.recv()
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = BufferCreator(reactor, Unbuffered).connectTCP('127.0.0.1', PORT)
        #>>> buf.write('hello')
        #>>> buf.recv()
        #'you said hello. '
        #>>> buf.recv()
        #Traceback
        # ...
        #ConnectionLost
        #>>> buf.recv()
        #''

        Note that server 'BYE' was received by twisted, but it was thrown away. Use Buffer if you
        want to keep the received data.
        """
        if self._queue is None:
            return ''
        try:
            return self._wait()
        except ConnectionDone:
            self._queue = None
            return ''
        except Exception:
            self._queue = None
            raise

    # iterator protocol:

    def __iter__(self):
        return self

    def next(self):
        """
        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Unbuffered).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> for data in buf:
        ...     print `data`
        'you said hello. '
        'BYE'
        """
        result = self.recv()
        if not result:
            raise StopIteration
        return result


class Buffer(BaseBuffer):

    protocol_class = Protocol

    def __init__(self):
        self.buf = ''

    def read(self, size=-1):
        """Like file's read().

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> buf.read(9)
        'you said '
        >>> buf.read(999)
        'hello. BYE'
        >>> buf.read(9)
        ''
        >>> buf.read(1)
        ''
        >>> print buf._queue
        None

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('world')
        >>> buf.read()
        'you said world. BYE'
        >>> buf.read()
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        #>>> buf.write('whoa')
        #>>> buf.read(4)
        #'you '
        #>>> buf.read()
        #Traceback
        # ...
        #ConnectionLost:
        #>>> buf._queue
        #None
        #>>> buf.read(4)
        #'said'
        #>>> buf.read()
        #' whoa. BYE'
        """
        if self._queue is not None:
            try:
                while len(self.buf) < size or size < 0:
                    recvd = self._wait()
                    self.buf += recvd
            except ConnectionDone:
                self._queue = None
            except Exception:
                self._queue = None
                # signal the error, but keep buf intact for possible inspection
                raise
        if size>=0:
            result, self.buf = self.buf[:size], self.buf[size:]
        else:
            result, self.buf = self.buf, ''
        return result

    def recv(self, buflen=None):
        """Like socket's recv().

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> buf.recv()
        'you said hello. '
        >>> buf.recv()
        'BYE'
        >>> buf.recv()
        ''
        >>> buf.recv()
        ''

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('whoa')
        >>> buf.recv(9)
        'you said '
        >>> buf.recv(999)
        'whoa. '
        >>> buf.recv(9)
        'BYE'
        >>> buf.recv(1)
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        #>>> buf.write('whoa')
        #>>> buf.recv()
        #'you said whoa. '
        #>>> buf.recv()
        #Traceback
        #   ConnectionLost
        #>>> buf.recv()
        #'BYE'
        #'hello. '
        #>>> buf.read(9)
        #'BYE'
        #>>> buf.read(1)
        """
        if self._queue is not None and not self.buf:
            try:
                recvd = self._wait()
                #print 'recvd: %r' % recvd
                self.buf += recvd
            except ConnectionDone:
                self._queue = None
            except Exception:
                self._queue = None
                # signal the error, but if buf had any data keep it
                raise
        if buflen is None:
            result, self.buf = self.buf, ''
        else:
            result, self.buf = self.buf[:buflen], self.buf[buflen:]
        return result

    # iterator protocol:

    def __iter__(self):
        return self

    def next(self):
        """
        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(reactor, Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> for data in buf:
        ...     print `data`
        'you said hello. '
        'BYE'
        """
        res = self.recv()
        if not res:
            raise StopIteration
        return res


def sync_connect(reactor, connect_func, protocol_instance, address_args, *args, **kwargs):
    d = defer.Deferred()
    f = _InstanceFactory(reactor, protocol_instance, d)
    connect_func(*(address_args + (f,) + args), **kwargs)
    protocol = block_on(d)

class BufferCreator(object):

    buffer_class = Buffer

    def __init__(self, reactor, buffer_class=None, *args, **kwargs):
        self.reactor = reactor
        if buffer_class is not None:
            self.buffer_class = buffer_class
        self.args = args
        self.kwargs = kwargs

    def connectTCP(self, host, port, *args, **kwargs):
        buffer = self.buffer_class(*self.args, **self.kwargs)
        protocol = buffer.build_protocol()
        sync_connect(self.reactor, self.reactor.connectTCP, protocol, (host, port), *args, **kwargs)
        return buffer

    def connectSSL(self, host, port, *args, **kwargs):
        buffer = self.buffer_class(*self.args, **self.kwargs)
        protocol = buffer.build_protocol()
        sync_connect(self.reactor, self.reactor.connectSSL, protocol, (host, port), *args, **kwargs)
        return buffer

    def connectTLS(self, host, port, *args, **kwargs):
        buffer = self.buffer_class(*self.args, **self.kwargs)
        protocol = buffer.build_protocol()
        sync_connect(self.reactor, self.reactor.connectTLS, protocol, (host, port), *args, **kwargs)
        return buffer

    def connectUNIX(self, address, *args, **kwargs):
        buffer = self.buffer_class(*self.args, **self.kwargs)
        protocol = buffer.build_protocol()
        sync_connect(self.reactor, self.reactor.connectUNIX, protocol, (address,), *args, **kwargs)
        return buffer

class SpawnFactory(Factory):

    buffer_class = Buffer

    def __init__(self, handler, buffer_class=None, *args, **kwargs):
        self.handler = handler
        if buffer_class is not None:
            self.buffer_class = buffer_class
        self.args = args
        self.kwargs = kwargs

    def buildProtocol(self, addr):
        buffer = self.buffer_class(*self.args, **self.kwargs)
        protocol = buffer.build_protocol()
        protocol.factory = self
        spawn(self.handler, buffer)
        return protocol


def __setup_server_tcp(exit='clean', delay=0.1, port=0):
    from eventlet.green import socket
    from eventlet.api import sleep
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', port))
    port = s.getsockname()[1]
    s.listen(5)
    s.settimeout(delay+1)
    def serve():
        conn, addr = s.accept()
        conn.settimeout(delay+1)
        hello = conn.recv(128)
        conn.sendall('you said %s. ' % hello)
        sleep(delay)
        conn.sendall('BYE')
        conn.close()
    spawn(serve)
    return port

if __name__ == '__main__':
    import doctest
    from twisted.internet import reactor
    doctest.testmod(extraglobs = {'setup_server_tcp': __setup_server_tcp})

