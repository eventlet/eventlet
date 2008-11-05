from eventlet.twistedutil.protocol import BufferCreator
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverBuffer

from twisted.internet import reactor

# read from TCP connection using default Buffer
conn = BufferCreator(reactor).connectTCP('www.google.com', 80)
conn.write('GET / HTTP/1.0\r\n\r\n')
print conn.read()

