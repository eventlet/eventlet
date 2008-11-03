"""Basic twisted protocols converted to synchronous mode"""
from twisted.internet.protocol import ClientCreator, Protocol as _Protocol
from twisted.protocols import basic
from twisted.internet.error import ConnectionDone
from twisted.internet.protocol import Factory, _InstanceFactory
from twisted.internet import defer

from eventlet.api import spawn
from eventlet.channel import channel
from eventlet.twisteds.util import block_on


def connectTCP(*args, **kwargs):
    from twisted.internet import reactor
    buffer_class = kwargs.pop('buffer_class', DEFAULT_BUFFER)
    cc = ClientCreator(reactor, buffer_class.protocol_class)
    protocol = block_on(cc.connectTCP(*args, **kwargs))
    chan = protocol.channel = channel()
    return buffer_class(protocol, chan)

def connectSSL(*args, **kwargs):
    from twisted.internet import reactor
    buffer_class = kwargs.pop('buffer_class', DEFAULT_BUFFER)
    cc = ClientCreator(reactor, buffer_class.protocol_class)
    protocol = block_on(cc.connectSSL(*args, **kwargs))
    chan = protocol.channel = channel()
    return buffer_class(protocol, chan)

def _connectTLS(protocol, host, port, *args, **kwargs):
    from twisted.internet import reactor
    d = defer.Deferred()
    f = _InstanceFactory(reactor, protocol, d)
    reactor.connectTLS(host, port, f, *args, **kwargs)
    return d

def connectTLS(host, port, *args, **kwargs):
    buffer_class = kwargs.pop('buffer_class', DEFAULT_BUFFER)
    protocol = block_on(_connectTLS(buffer_class.protocol_class(), host, port, *args, **kwargs))
    chan = protocol.channel = channel()
    return buffer_class(protocol, chan)

def listenTCP(port, handler, *args, **kwargs):
    from twisted.internet import reactor
    buffer_class = kwargs.pop('buffer_class', unbuffered)
    return reactor.listenTCP(port, SpawnFactory(buffer_class, handler), *args, **kwargs)

def listenSSL(port, handler, *args, **kwargs):
    from twisted.internet import reactor
    buffer_class = kwargs.pop('buffer_class', unbuffered)
    return reactor.listenSSL(port, SpawnFactory(buffer_class, handler), *args, **kwargs)

def listenTLS(port, handler, *args, **kwargs):
    from twisted.internet import reactor
    buffer_class = kwargs.pop('buffer_class', unbuffered)
    return reactor.listenTLS(port, SpawnFactory(buffer_class, handler), *args, **kwargs)

class SpawnFactory(Factory):

    def __init__(self, buffer_class, handler):
        self.handler = handler
        self.buffer_class = buffer_class
        self.protocol = buffer_class.protocol_class

    def buildProtocol(self, addr):
        protocol = self.protocol()
        chan = protocol.channel = channel()
        protocol.factory = self
        spawn(self.handler, self.buffer_class(protocol, chan))
        return protocol


class buffer_base(object):

    def __init__(self, protocol, channel):
        self.protocol = protocol
        self.channel = channel

    @property
    def transport(self):
        return self.protocol.transport

    def __getattr__(self, item):
        return getattr(self.protocol.transport, item)


class Protocol(_Protocol):

    def dataReceived(self, data):
        spawn(self.channel.send, data)

    def connectionLost(self, reason):
        self.channel.send_exception(reason.value)
        self.channel = None # QQQ channel creates a greenlet. does it actually finish and memory is reclaimed?


class unbuffered(buffer_base):

    protocol_class = Protocol

    def recv(self):
        """Receive a single chunk of undefined size.

        Return '' if connection was closed cleanly, raise the exception if it was closed
        in a non clean fashion. After that all successive calls return ''.

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = connectTCP('127.0.0.1', PORT, buffer_class=unbuffered)
        >>> buf.write('hello')
        >>> buf.recv()
        'you said hello. '
        >>> buf.recv()
        'BYE'
        >>> buf.recv()
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = connectTCP('127.0.0.1', PORT, buffer_class=unbuffered)
        #>>> buf.write('hello')
        #>>> buf.recv()
        #'you said hello. '
        #>>> buf.recv()
        #Traceback
        # ...
        #ConnectionLost
        #>>> buf.recv()
        #''

        Note that server 'BYE' was received by twisted, but it was thrown away. Use buffer if you
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
        >>> buf = connectTCP('127.0.0.1', setup_server_tcp(exit='clean'), buffer_class=unbuffered)
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


class buffer(buffer_base):
    
    protocol_class = Protocol

    def __init__(self, *args):
        buffer_base.__init__(self, *args)
        self.buf = ''

    def read(self, size=-1):
        """Like file's read().

        >>> PORT = setup_server_tcp(exit='clean')
        >>> buf = connectTCP('127.0.0.1', PORT)
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
        >>> buf = connectTCP('127.0.0.1', PORT)
        >>> buf.write('world')
        >>> buf.read()
        'you said world. BYE'
        >>> buf.read()
        ''

        #>>> PORT = setup_server_tcp(exit='reset')
        #>>> buf = connectTCP('127.0.0.1', PORT)
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
        >>> buf = connectTCP('127.0.0.1', PORT)
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
        >>> buf = connectTCP('127.0.0.1', PORT)
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
        #>>> buf = connectTCP('127.0.0.1', PORT)
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
        >>> buf = connectTCP('127.0.0.1', setup_server_tcp(exit='clean'))
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

DEFAULT_BUFFER = buffer


class LineOnlyReceiver(basic.LineOnlyReceiver):

    def lineReceived(self, line):
        spawn(self.channel.send, line)

    def connectionLost(self, reason):
        self.channel.send_exception(reason.value)


class line_only_receiver(buffer_base):

    protocol_class = LineOnlyReceiver

    def readline(self):
        return self.channel.receive()

    def sendline(self, line):
        self.protocol.sendLine(line)

    # iterator protocol:

    def __iter__(self):
        return self

    def next(self):
        try:
            return self.readline()
        except ConnectionDone:
            raise StopIteration

