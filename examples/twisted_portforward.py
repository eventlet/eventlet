import sys
from twisted.internet import reactor
from eventlet.coros import event, Job
from eventlet.twistedutil import join_reactor
from eventlet.twistedutil.protocol import GreenClientCreator, SpawnFactory, UnbufferedTransport

def forward(from_, to):
    try:
        while True:
            x = from_.recv()
            if not x:
                break
            print 'forwarding %s bytes' % len(x)
            to.write(x)
    finally:
        to.loseConnection()

def handler(local):
    remote = GreenClientCreator(reactor, UnbufferedTransport).connectTCP(remote_host, remote_port)
    error = event()
    a = Job.spawn_new(forward, remote, local)
    b = Job.spawn_new(forward, local, remote)
    a.wait()
    b.wait()

local_port, remote_host, remote_port = sys.argv[1:]
local_port = int(local_port)
remote_port = int(remote_port)
reactor.listenTCP(local_port, SpawnFactory(handler))
reactor.run()
