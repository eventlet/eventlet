#!/usr/bin/python
"""Port forwarder
USAGE: twisted_portforward.py local_port remote_host remote_port"""
import sys
from twisted.internet import reactor
from eventlet.coros import Job
from eventlet.twistedutil import join_reactor
from eventlet.twistedutil.protocol import GreenClientCreator, SpawnFactory, UnbufferedTransport

def forward(source, dest):
    try:
        while True:
            x = source.recv()
            if not x:
                break
            print 'forwarding %s bytes' % len(x)
            dest.write(x)
    finally:
        dest.loseConnection()

def handler(local):
    client = str(local.getHost())
    print 'accepted connection from %s' % client
    remote = GreenClientCreator(reactor, UnbufferedTransport).connectTCP(remote_host, remote_port)
    a = Job.spawn_new(forward, remote, local)
    b = Job.spawn_new(forward, local, remote)
    a.wait()
    b.wait()
    print 'closed connection to %s' % client

try:
    local_port, remote_host, remote_port = sys.argv[1:]
except ValueError:
    sys.exit(__doc__)
local_port = int(local_port)
remote_port = int(remote_port)
reactor.listenTCP(local_port, SpawnFactory(handler))
reactor.run()
