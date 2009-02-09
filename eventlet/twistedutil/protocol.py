# Copyright (c) 2008-2009 AG Projects
# Author: Denis Bilenko
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Basic twisted protocols converted to synchronous mode"""
from twisted.internet.protocol import Protocol as twistedProtocol
from twisted.internet.error import ConnectionDone
from twisted.internet.protocol import Factory, ClientFactory

from twisted.internet.interfaces import IHalfCloseableProtocol
from zope.interface import implements

from eventlet import proc
from eventlet.api import getcurrent
from eventlet.coros import queue, event


class ReadConnectionDone(ConnectionDone):
    pass

class WriteConnectionDone(ConnectionDone):
    pass

class ValueQueue(queue):

    def wait(self):
        """The difference from queue.wait: if there is an only item in the
        queue and it is an exception, raise it, but keep it in the queue, so
        that future calls to wait() will raise it again.
        """
        self.sem.acquire()
        if self.has_final_error():
            # the last item, which is an exception, raise without emptying the queue
            self.sem.release()
            getcurrent().throw(*self.items[0][1])
        else:
            result, exc = self.items.popleft()
            if exc is not None:
                getcurrent().throw(*exc)
            return result

    def has_final_error(self):
        return len(self.items)==1 and self.items[0][1] is not None


class Event(event):

    def send(self, value, exc=None):
        if self.ready():
            self.reset()
        return event.send(self, value, exc)

    def send_exception(self, *throw_args):
        if self.ready():
            self.reset()
        return event.send_exception(self, *throw_args)


class Producer2Event(object):

    # implements IPullProducer

    def __init__(self, event):
        self.event = event

    def resumeProducing(self):
        self.event.send(1)

    def stopProducing(self):
        del self.event


class GreenTransportBase(object):

    transportBufferSize = None

    def __init__(self, transportBufferSize=None):
        if transportBufferSize is not None:
            self.transportBufferSize = transportBufferSize
        self._queue = queue()
        self._read_disconnected_event = Event()
        self._write_disconnected_event = Event()
        self._write_event = Event()

    def build_protocol(self):
        protocol = self.protocol_class(self)
        return protocol

    def _got_transport(self, transport):
        self._queue.send(transport)

    def _got_data(self, data):
        self._queue.send(data)

    def _connectionLost(self, reason):
        self._read_disconnected_event.send(reason.value)
        self._write_disconnected_event.send(reason.value)
        self._queue.send_exception(reason.value)
        self._write_event.send_exception(reason.value)

    def _readConnectionLost(self):
        self._read_disconnected_event.send(ReadConnectionDone)
        self._queue.send_exception(ReadConnectionDone)

    def _writeConnectionLost(self):
        self._write_disconnected_event.send(WriteConnectionDone)
        self._write_event.send_exception(WriteConnectionDone)

    def _wait(self):
        if self._read_disconnected_event.ready():
            if self._queue:
                return self._queue.wait()
            else:
                raise self._read_disconnected_event.wait()
        self.resumeProducing()
        try:
            return self._queue.wait()
        finally:
            self.pauseProducing()

    def write(self, data):
        if self._write_disconnected_event.ready():
            raise self._write_disconnected_event.wait()
        self._write_event.reset()
        self.transport.write(data)
        self._write_event.wait()

    def async_write(self, data):
        self.transport.write(data)

    def loseConnection(self):
        self.transport.unregisterProducer()
        self.transport.loseConnection()
        self._read_disconnected_event.wait()
        self._write_disconnected_event.wait()

    def loseWriteConnection(self):
        self.transport.unregisterProducer()
        self.transport.loseWriteConnection()
        self._write_disconnected_event.wait()

    def __getattr__(self, item):
        if item=='transport':
            raise AttributeError(item)
        if hasattr(self, 'transport'):
            try:
                return getattr(self.transport, item)
            except AttributeError:
                me = type(self).__name__
                trans = type(self.transport).__name__
                raise AttributeError("Neither %r nor %r has attribute %r" % (me, trans, item))
        else:
            raise AttributeError(item)

    def resumeProducing(self):
        self.paused -= 1
        if self.paused==0:
            if self.transport.connected and not self.transport.disconnecting:
                self.transport.resumeProducing()

    def pauseProducing(self):
        self.paused += 1
        if self.paused==1:
            self.transport.pauseProducing()

    def _init_transport_producer(self):
        self.transport.pauseProducing()
        self.paused = 1

    def _init_transport(self):
        transport = self._queue.wait()
        self.transport = transport
        if self.transportBufferSize is not None:
            transport.bufferSize = self.transportBufferSize
        self._init_transport_producer()
        transport.registerProducer(Producer2Event(self._write_event), False)


class Protocol(twistedProtocol):

    implements(IHalfCloseableProtocol)

    def __init__(self, recepient):
        self._recepient = recepient

    def connectionMade(self):
        self._recepient._got_transport(self.transport)

    def dataReceived(self, data):
        self._recepient._got_data(data)

    def connectionLost(self, reason):
        self._recepient._connectionLost(reason)

    def readConnectionLost(self):
        self._recepient._readConnectionLost()

    def writeConnectionLost(self):
        self._recepient._writeConnectionLost()


class UnbufferedTransport(GreenTransportBase):
    """A very simple implementation of a green transport without an additional buffer"""

    protocol_class = Protocol

    def recv(self):
        """Receive a single chunk of undefined size.

        Return '' if connection was closed cleanly, raise the exception if it was closed
        in a non clean fashion. After that all successive calls return ''.
        """
        if self._read_disconnected_event.ready():
            return ''
        try:
            return self._wait()
        except ConnectionDone:
            return ''

    def read(self):
        """Read the data from the socket until the connection is closed cleanly.

        If connection was closed in a non-clean fashion, the appropriate exception
        is raised. In that case already received data is lost.
        Next time read() is called it returns ''.
        """
        result = ''
        while True:
            recvd = self.recv()
            if not recvd:
                break
            result += recvd
        return result

    # iterator protocol:

    def __iter__(self):
        return self

    def next(self):
        result = self.recv()
        if not result:
            raise StopIteration
        return result


class GreenTransport(GreenTransportBase):

    protocol_class = Protocol
    _buffer = ''
    _error = None

    def read(self, size=-1):
        """Read size bytes or until EOF"""
        if not self._read_disconnected_event.ready():
            try:
                while len(self._buffer) < size or size < 0:
                    self._buffer += self._wait()
            except ConnectionDone:
                pass
            except:
                if not self._read_disconnected_event.has_exception():
                    raise
        if size>=0:
            result, self._buffer = self._buffer[:size], self._buffer[size:]
        else:
            result, self._buffer = self._buffer, ''
        if not result and self._read_disconnected_event.has_exception():
            try:
                self._read_disconnected_event.wait()
            except ConnectionDone:
                pass
        return result

    def recv(self, buflen=None):
        """Receive a single chunk of undefined size but no bigger than buflen"""
        if not self._read_disconnected_event.ready():
            self.resumeProducing()
            try:
                try:
                    recvd = self._wait()
                    #print 'received %r' % recvd
                    self._buffer += recvd
                except ConnectionDone:
                    pass
                except:
                    if not self._read_disconnected_event.has_exception():
                        raise
            finally:
                self.pauseProducing()
        if buflen is None:
            result, self._buffer = self._buffer, ''
        else:
            result, self._buffer = self._buffer[:buflen], self._buffer[buflen:]
        if not result and self._read_disconnected_event.has_exception():
            try:
                self._read_disconnected_event.wait()
            except ConnectionDone:
                pass
        return result

    # iterator protocol:

    def __iter__(self):
        return self

    def next(self):
        res = self.recv()
        if not res:
            raise StopIteration
        return res


class GreenInstanceFactory(ClientFactory):

    def __init__(self, instance, event):
        self.instance = instance
        self.event = event

    def buildProtocol(self, addr):
        return self.instance

    def clientConnectionFailed(self, connector, reason):
        self.event.send_exception(reason.type, reason.value, reason.tb)


class GreenClientCreator(object):
    """Connect to a remote host and return a connected green transport instance.
    """

    gtransport_class = GreenTransport

    def __init__(self, reactor=None, gtransport_class=None, *args, **kwargs):
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        if gtransport_class is not None:
            self.gtransport_class = gtransport_class
        self.args = args
        self.kwargs = kwargs

    def _make_transport_and_factory(self):
        gtransport = self.gtransport_class(*self.args, **self.kwargs)
        protocol = gtransport.build_protocol()
        factory = GreenInstanceFactory(protocol, gtransport._queue)
        return gtransport, factory

    def connectTCP(self, host, port, *args, **kwargs):
        gtransport, factory = self._make_transport_and_factory()
        self.reactor.connectTCP(host, port, factory, *args, **kwargs)
        gtransport._init_transport()
        return gtransport

    def connectSSL(self, host, port, *args, **kwargs):
        gtransport, factory = self._make_transport_and_factory()
        self.reactor.connectSSL(host, port, factory, *args, **kwargs)
        gtransport._init_transport()
        return gtransport

    def connectTLS(self, host, port, *args, **kwargs):
        gtransport, factory = self._make_transport_and_factory()
        self.reactor.connectTLS(host, port, factory, *args, **kwargs)
        gtransport._init_transport()
        return gtransport

    def connectUNIX(self, address, *args, **kwargs):
        gtransport, factory = self._make_transport_and_factory()
        self.reactor.connectUNIX(address, factory, *args, **kwargs)
        gtransport._init_transport()
        return gtransport

    def connectSRV(self, service, domain, *args, **kwargs):
        SRVConnector = kwargs.pop('ConnectorClass', None)
        if SRVConnector is None:
            from twisted.names.srvconnect import SRVConnector
        gtransport, factory = self._make_transport_and_factory()
        c = SRVConnector(self.reactor, service, domain, factory, *args, **kwargs)
        c.connect()
        gtransport._init_transport()
        return gtransport


class SimpleSpawnFactory(Factory):
    """Factory that spawns a new greenlet for each incoming connection.

    For an incoming connection a new greenlet is created using the provided
    callback as a function and a connected green transport instance as an
    argument.
    """

    gtransport_class = GreenTransport

    def __init__(self, handler, gtransport_class=None, *args, **kwargs):
        self.handler = handler
        if gtransport_class is not None:
            self.gtransport_class = gtransport_class
        self.args = args
        self.kwargs = kwargs

    def buildProtocol(self, addr):
        gtransport = self.gtransport_class(*self.args, **self.kwargs)
        protocol = gtransport.build_protocol()
        protocol.factory = self
        self._do_spawn(gtransport, protocol)
        return protocol

    def _do_spawn(self, gtransport, protocol):
        proc.spawn_greenlet(self._run_handler, gtransport, protocol)

    def _run_handler(self, gtransport, protocol):
        gtransport._init_transport()
        self.handler(gtransport)


class SpawnFactory(SimpleSpawnFactory):
    """An extension to SimpleSpawnFactory that provides some control over
    the greenlets it has spawned.
    """

    def __init__(self, handler, gtransport_class=None, *args, **kwargs):
        self.greenlets = set()
        SimpleSpawnFactory.__init__(self, handler, gtransport_class, *args, **kwargs)

    def _do_spawn(self, gtransport, protocol):
        g = proc.spawn(self._run_handler, gtransport, protocol)
        self.greenlets.add(g)
        g.link(lambda *_: self.greenlets.remove(g))

    def waitall(self):
        return proc.waitall(self.greenlets)

