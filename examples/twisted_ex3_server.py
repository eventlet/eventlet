from twisted.internet import pollreactor; pollreactor.install()
from twisted.internet.protocol import Factory
from twisted.internet import reactor
from twisted.protocols import basic
from twisted.internet.error import ConnectionDone

from eventlet.api import spawn, get_hub
from eventlet.channel import channel

class LineOnlyReceiver(basic.LineOnlyReceiver):

    def __init__(self, channel):
        self.channel = channel

    def lineReceived(self, line):
        spawn(self.channel.send, line)

    def connectionLost(self, reason):
        self.channel.send_exception(reason.value)


class line_only_receiver:

    def __init__(self, protocol, channel):
        self.protocol = protocol
        self.channel = channel

    def readline(self):
        return self.channel.receive()

    def send(self, data):
        self.protocol.transport.write(data)

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


class MyFactory(Factory):
    protocol = LineOnlyReceiver

    def __init__(self, handler):
        self.handler = handler

    def buildProtocol(self, addr):
        ch = channel()
        p = self.protocol(ch)
        p.factory = self
        spawn(self.handler, line_only_receiver(p, ch))
        return p

def handler(linerecv):
    peer = linerecv.protocol.transport.getPeer()
    print 'new connection from %s' % (peer, )
    try:
        for line in linerecv:
            print 'received from %s: %s' % (peer, line)
        print peer, 'connection done'
    except Exception, ex:
        print peer, ex

reactor.listenTCP(8007, MyFactory(handler))
get_hub().switch()
