"""Basic twisted protocols converted to synchronous mode"""
from twisted.internet.protocol import Protocol as twistedProtocol
from twisted.internet.error import ConnectionDone
from twisted.internet.protocol import Factory, _InstanceFactory
from twisted.internet import defer

from eventlet.api import spawn
from eventlet.channel import channel
from eventlet.twistedutil import block_on


class BaseBuffer(object):

    def __init__(self, protocol, channel):
        self.protocol = protocol
        self.channel = channel

    @property
    def transport(self):
        return self.protocol.transport

    def __getattr__(self, item):
        return getattr(self.protocol.transport, item)


class Protocol(twistedProtocol):

    def dataReceived(self, data):
        spawn(self.channel.send, data)

    def connectionLost(self, reason):
        self.channel.send_exception(reason.value)
        self.channel = None # QQQ channel creates a greenlet. does it actually finish and memory is reclaimed?


class Unbuffered(BaseBuffer):

    protocol_class = Protocol

    def recv(self):
        """Receive a single chunk of undefined size.

        Return '' if connection was closed cleanly, raise the exception if it was closed
        in a non clean fashion. After that all successive calls return ''.

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(Unbuffered).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> buf.recv()
        'you said hello. '
        >>> buf.recv()
        'BYE'
        >>> buf.recv()
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = BufferCreator(Unbuffered).connectTCP('127.0.0.1', PORT)
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
        if self.channel is None:
            return ''
        try:
            return self.channel.receive()
        except ConnectionDone:
            self.channel = None
            return ''
        except Exception:
            self.channel = None
            raise

    # iterator protocol:

    def __iter__(self):
        return self

    def next(self):
        """
        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(Unbuffered).connectTCP('127.0.0.1', PORT)
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

    def __init__(self, *args):
        BaseBuffer.__init__(self, *args)
        self.buf = ''

    def read(self, size=-1):
        """Like file's read().

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('hello')
        >>> buf.read(9)
        'you said '
        >>> buf.read(999)
        'hello. BYE'
        >>> buf.read(9)
        ''
        >>> buf.read(1)
        ''
        >>> print buf.channel
        None

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
        >>> buf.write('world')
        >>> buf.read()
        'you said world. BYE'
        >>> buf.read()
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
        #>>> buf.write('whoa')
        #>>> buf.read(4)
        #'you '
        #>>> buf.read()
        #Traceback
        # ...
        #ConnectionLost:
        #>>> buf.channel
        #None
        #>>> buf.read(4)
        #'said'
        #>>> buf.read()
        #' whoa. BYE'
        """
        if self.channel is not None:
            try:
                while len(self.buf) < size or size < 0:
                    recvd = self.channel.receive()
                    self.buf += recvd
            except ConnectionDone:
                self.channel = None
            except Exception:
                self.channel = None
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
        >>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
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
        >>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
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
        #>>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
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
        if self.channel is not None and not self.buf:
            try:
                recvd = self.channel.receive()
                #print 'recvd: %r' % recvd
                self.buf += recvd
            except ConnectionDone:
                self.channel = None
            except Exception:
                self.channel = None
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
        >>> buf = BufferCreator(Buffer).connectTCP('127.0.0.1', PORT)
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


def connectXXX(reactor, connect_func, protocol_instance, address_args, *args, **kwargs):
    d = defer.Deferred()
    f = _InstanceFactory(reactor, protocol_instance, d)
    connect_func(*(address_args + (f,) + args), **kwargs)
    protocol = block_on(d)
    chan = protocol.channel = channel()
    return (protocol, chan)

class BufferCreator(object):

    buffer_class = Buffer

    def __init__(self, buffer_class=None, reactor=None, protocol_args=None, protocol_kwargs=None):
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        if buffer_class is not None:
            self.buffer_class = buffer_class
        self.protocol_args = protocol_args or ()
        self.protocol_kwargs = protocol_kwargs or {}

    def connectTCP(self, host, port, *args, **kwargs):
        protocol = self.buffer_class.protocol_class(*self.protocol_args, **self.protocol_kwargs)
        protocol, chan = connectXXX(self.reactor, self.reactor.connectTCP,
                                    protocol, (host, port), *args, **kwargs)
        return self.buffer_class(protocol, chan)

    def connectSSL(self, host, port, *args, **kwargs):
        protocol = self.buffer_class.protocol_class(*self.protocol_args, **self.protocol_kwargs)
        protocol, chan = connectXXX(self.reactor, self.reactor.connectSSL,
                                    protocol, (host, port), *args, **kwargs)
        return self.buffer_class(protocol, chan)

    def connectTLS(self, host, port, *args, **kwargs):
        protocol = self.buffer_class.protocol_class(*self.protocol_args, **self.protocol_kwargs)
        protocol, chan = connectXXX(self.reactor, self.reactor.connectTLS,
                                    protocol, (host, port), *args, **kwargs)
        return self.buffer_class(protocol, chan)

    def connectUNIX(self, address, *args, **kwargs):
        protocol = self.buffer_class.protocol_class(*self.protocol_args, **self.protocol_kwargs)
        protocol, chan = connectXXX(self.reactor, self.reactor.connectTCP,
                                    protocol, (address, ), *args, **kwargs)
        return self.buffer_class(protocol, chan) 

class SpawnFactory(Factory):

    buffer_class = Buffer

    def __init__(self, handler, buffer_class=None):
        self.handler = handler
        if buffer_class is not None:
            self.buffer_class = buffer_class
        self.protocol = self.buffer_class.protocol_class

    def buildProtocol(self, addr):
        protocol = self.protocol()
        chan = protocol.channel = channel()
        protocol.factory = self
        spawn(self.handler, self.buffer_class(protocol, chan))
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

