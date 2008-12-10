from twisted.protocols import basic
from twisted.internet.error import ConnectionDone
from eventlet.twistedutil.protocol import GreenTransportBase

class LineOnlyReceiver(basic.LineOnlyReceiver):

    def __init__(self, gtransport, queue):
        self.gtransport = gtransport
        self._queue = queue
    
    def connectionMade(self):
        self.gtransport.init_transport(self.transport)
        del self.gtransport

    def lineReceived(self, line):
        self._queue.send(line)

    def connectionLost(self, reason):
        self._queue.send_exception(reason.type, reason.value, reason.tb)

class LineOnlyReceiverTransport(GreenTransportBase):

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

