from twisted.protocols import basic
from twisted.internet.error import ConnectionDone
from eventlet.twistedutil.protocol import BaseBuffer

class LineOnlyReceiver(basic.LineOnlyReceiver):

    def lineReceived(self, line):
        self._queue.send(line)

    def connectionLost(self, reason):
        self._queue.send_exception(reason.value)

class LineOnlyReceiverBuffer(BaseBuffer):

    protocol_class = LineOnlyReceiver

    def readline(self):
        return self._wait()

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

