from twisted.internet import ssl
from twisted.internet.error import ConnectionClosed
from eventlet.twistedutil.protocol import BufferCreator
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverBuffer

from twisted.internet import reactor

# read from TCP connection using default Buffer
conn = BufferCreator(reactor).connectTCP('www.google.com', 80)
conn.write('GET / HTTP/1.0\r\n\r\n')
print conn.read()

# read from SSL connection line by line
conn = BufferCreator(reactor, LineOnlyReceiverBuffer).connectSSL('sf.net', 443, ssl.ClientContextFactory())
conn.write('GET / HTTP/1.0\r\n\r\n')
try:
    for num, line in enumerate(conn):
        print '%3s %r' % (num, line)
except ConnectionClosed, ex:
    print ex

