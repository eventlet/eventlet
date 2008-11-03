from eventlet.twisteds import basic
from eventlet.twisteds import join_reactor

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
basic.listenTCP(8007, chat.handler, 8007, buffer_class=basic.line_only_receiver)
from twisted.internet import reactor
reactor.run()
