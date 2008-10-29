"""Basic twisted protocols converted to synchronous mode"""
from twisted.internet.protocol import ClientCreator
from twisted.protocols import basic
from twisted.internet import reactor
from twisted.internet.error import ConnectionDone
from twisted.internet.protocol import Factory

from eventlet.api import spawn
from eventlet.channel import channel
from eventlet.twisteds.util import block_on


def connectTCP(buffer_class, host, port):
    cc = ClientCreator(reactor, buffer_class.protocol_class)
    protocol = block_on(cc.connectTCP(host, port))
    chan = protocol.channel = channel()
    return buffer_class(protocol, chan)

def listenTCP(buffer_class, handler, port, *args, **kwargs):
    from twisted.internet import reactor
    return reactor.listenTCP(port, SpawnFactory(buffer_class, handler), *args, **kwargs)

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

    def send(self, data):
        self.protocol.transport.write(data)

    def close(self):
        self.protocol.transport.loseConnection()

    @property
    def transport(self):
        return self.protocol.transport

    def __getattr__(self, item):
        return getattr(self.protocol.transport, item)

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

