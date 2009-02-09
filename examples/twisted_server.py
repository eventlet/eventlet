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

"""Simple chat demo application.
Listen on port 8007 and re-send all the data received to other participants.

Demonstrates how to
 * plug in eventlet into a twisted application (join_reactor)
 * how to use SpawnFactory to start a new greenlet for each new request.
"""
from eventlet.twistedutil import join_reactor
from eventlet.twistedutil.protocol import SpawnFactory
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverTransport

class Chat:

    def __init__(self):
        self.participants = []

    def handler(self, conn):
        peer = conn.getPeer()
        print 'new connection from %s' % (peer, )
        conn.write("Welcome! There're %s participants already\n" % (len(self.participants)))
        self.participants.append(conn)
        try:
            for line in conn:
                if line:
                    print 'received from %s: %s' % (peer, line)
                    for buddy in self.participants:
                        if buddy is not conn:
                            buddy.sendline('from %s: %s' % (peer, line))
        except Exception, ex:
            print peer, ex
        else:
            print peer, 'connection done'
        finally:
            conn.loseConnection()
            self.participants.remove(conn)

print __doc__
chat = Chat()
from twisted.internet import reactor
reactor.listenTCP(8007, SpawnFactory(chat.handler, LineOnlyReceiverTransport))
reactor.run()

