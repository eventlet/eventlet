from twisted.protocols import basic
from twisted.internet.error import ConnectionDone
from eventlet.api import spawn
from eventlet.twistedutil.protocol import BaseBuffer

class LineOnlyReceiver(basic.LineOnlyReceiver):

    def lineReceived(self, line):
        spawn(self.channel.send, line)

    def connectionLost(self, reason):
        self.channel.send_exception(reason.value)

class LineOnlyReceiverBuffer(BaseBuffer):

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

