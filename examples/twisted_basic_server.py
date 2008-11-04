from eventlet.twistedutil import join_reactor
from eventlet.twistedutil.protocol import SpawnFactory
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverBuffer

class Chat:

    def __init__(self):
        self.participants = []

    def handler(self, conn):
        peer = conn.getPeer()
        print 'new connection from %s' % (peer, )
        self.participants.append(conn)
        try:
            for line in conn:
                print 'received from %s: %s' % (peer, line)
                for buddy in self.participants:
                    if buddy is not conn:
                        buddy.sendline('from %s: %s' % (peer, line))
        except Exception, ex:
            print peer, ex
        else:
            print peer, 'connection done'
        finally:
            self.participants.remove(conn)

chat = Chat()
from twisted.internet import reactor
reactor.listenTCP(8007, SpawnFactory(chat.handler, LineOnlyReceiverBuffer))
reactor.run()
