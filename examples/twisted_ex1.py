from twisted.internet import pollreactor; pollreactor.install()
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor

from eventlet.green import socket
from eventlet.api import spawn
from eventlet import coros

class Echo(Protocol):
    def dataReceived(self, data):
        print 'server received: %r' % data
        self.transport.write('you said %s' % data)

factory = Factory()
factory.protocol = Echo
reactor.listenTCP(34567, factory)

N=4
count = coros.metaphore()
count.inc(N)

def client():
    try:
        c = socket.socket()
        c.connect(('127.0.0.1', 34567))
        c.send('hello')
        print 'client received: %s' % c.recv(1024)
        c.send('bye')
        print 'client received: %s' % c.recv(1024)
    finally:
        count.dec()

for x in range(N):
    # note that spawn doesn't switch to new greenlet immediately.
    spawn(client)

# the execution ends with the main greenlet's exit (by design), so we need to pause here
count.wait()
