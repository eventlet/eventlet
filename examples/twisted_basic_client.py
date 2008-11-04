from eventlet.twistedutil.protocol import BufferCreator
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverBuffer

conn = BufferCreator(LineOnlyReceiverBuffer).connectTCP('www.google.com', 80)
conn.write('GET / HTTP/1.0\r\n\r\n')
for line in conn:
    print line

