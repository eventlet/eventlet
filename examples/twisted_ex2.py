"wrapping twisted protocol using a channel and block_on()"
from twisted.internet import pollreactor; pollreactor.install()
from twisted.internet.protocol import ClientCreator
from twisted.protocols import basic
from twisted.internet import reactor
from twisted.internet.error import ConnectionDone

from eventlet.api import spawn
from eventlet.channel import channel
from eventlet.twisteds.util import block_on


class LineOnlyReceiver(basic.LineOnlyReceiver):

    def lineReceived(self, line):
        spawn(self.channel.send, line)

    def connectionLost(self, reason):
        self.channel.send_exception(reason.value)


class line_only_receiver:

    def __init__(self, host, port):
        cc = ClientCreator(reactor, LineOnlyReceiver)
        self.protocol = block_on(cc.connectTCP(host, port))
        self.protocol.channel = self.channel = channel()

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


conn = line_only_receiver('www.google.com', 80)
conn.send('GET / HTTP/1.0\r\n\r\n')
for line in conn:
    print line
