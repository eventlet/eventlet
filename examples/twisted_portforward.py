#!/usr/bin/python
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

"""Port forwarder
USAGE: twisted_portforward.py local_port remote_host remote_port"""
import sys
from twisted.internet import reactor
from eventlet.twistedutil import join_reactor
from eventlet.twistedutil.protocol import GreenClientCreator, SpawnFactory, UnbufferedTransport
from eventlet import proc

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
    a = proc.spawn(forward, remote, local)
    b = proc.spawn(forward, local, remote)
    proc.waitall([a, b], trap_errors=True)
    print 'closed connection to %s' % client

try:
    local_port, remote_host, remote_port = sys.argv[1:]
except ValueError:
    sys.exit(__doc__)
local_port = int(local_port)
remote_port = int(remote_port)
reactor.listenTCP(local_port, SpawnFactory(handler))
reactor.run()
